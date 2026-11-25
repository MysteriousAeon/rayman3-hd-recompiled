#!/usr/bin/env python3
"""G6-P127 / G6-P128 (D-362, D-363, E-608, E-609) offline regression for the HD+ Grand Minimus crown cutout.

Verifies without launching the game or modifying `external/rexglue-sdk`:
  1. Static invariants of `tools/g6p127_crown_blend.h` (all 10 verified bundles, `R3HD_CROWN_CUTOUT` +
     `R3HD_TEST_CROWN_BLEND` precedence, fail-closed checks, no `knaar_60.lvl` / `gum_crown`, no proprietary bytes).
  2. Real C++20 compilation and execution (`clang++ -std=c++20 -Wall -Wextra -Werror`) testing:
     - Precedence matrix (`ResolveEnabled`) across Vanilla/HD+/Custom production values and diagnostic fallback.
     - All 10 verified bundle filenames in `kCrownRecords` (exact lookup, case-insensitive, no substring match).
     - Synthetic fixtures: exact 1-byte `0x03 -> 0x08` diff, disk untouched, idempotency, 1-byte & non-overlapping reads.
     - Fail-closed refusals: wrong filename (`wood_19.lvl`, `knaar_60.lvl`, `fix.lvl`), wrong size (`kRefusedSize`),
       wrong header (`kRefusedHeader`), wrong flags & wrong tex record (`kRefusedSignature`), wrong original byte
       (`kRefusedSourceByte`), altered record hash (`kRefusedStoredHash`), unexpected caller buffer byte.
     - M33 mod ordering: M33 applied after crown overlay still wins on the same byte.
     - Optional read-only validation against all 10 local `.lvl` files + `knaar_60.lvl` negative check when present
       under `private/` (skipped cleanly in public/clean environments without proprietary game files).
  3. Settings, presets, persistence/migration, Windows/Linux launcher compatibility, EN/TR UI strings, existing
     correction independence, patch-script idempotency, and build-chain / SDK ordering.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import r3hd_settings as r3s

HEADER = ROOT / "tools" / "g6p127_crown_blend.h"
PATCH = ROOT / "tools" / "g6p127_crown_blend_patch.py"
BAT = ROOT / "tools" / "build_milestone8.bat"
REGISTRY = ROOT / "config" / "settings" / "registry.json"
UI_STRINGS = ROOT / "config" / "settings" / "ui_strings.json"
PLAY_PS1 = ROOT / "tools" / "play.ps1"
LINUX_PLAY = ROOT / "tools" / "linux" / "r3hd_play.py"
DEVENV = ROOT / "tools" / "devenv.bat"
SDK = ROOT / "external" / "rexglue-sdk"
GAMEDATA = ROOT / "private" / "extracted" / "5841123F" / "GAMEDATAbin"

VERIFIED_BUNDLES = [
    "menu_00", "fact_40", "fact_50", "fact_55",
    "knaar_10", "knaar_20", "knaar_30", "knaar_45", "knaar_70", "staff",
]

checks = failures = skipped = 0


def check(cond: bool, label: str) -> None:
    global checks, failures
    checks += 1
    if not cond:
        failures += 1
        print(f"FAIL {label}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


CPP_HARNESS = r'''
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>
#include "g6p127_crown_blend.h"

static int g_checks = 0;
static int g_fails = 0;
static std::vector<std::string> g_logs;

static void TestLog(const char* line) {
  g_logs.emplace_back(line ? line : "");
}

static void expect(bool cond, const char* msg) {
  ++g_checks;
  if (!cond) {
    ++g_fails;
    std::printf("CPP_FAIL %s\n", msg);
  }
}

static void WriteBE32(std::vector<uint8_t>& buf, size_t off, uint32_t v) {
  buf[off + 0] = uint8_t((v >> 24) & 0xFFu);
  buf[off + 1] = uint8_t((v >> 16) & 0xFFu);
  buf[off + 2] = uint8_t((v >> 8) & 0xFFu);
  buf[off + 3] = uint8_t(v & 0xFFu);
}

static void WriteFile(const std::filesystem::path& p, const std::vector<uint8_t>& data) {
  std::ofstream f(p, std::ios::binary | std::ios::trunc);
  f.write(reinterpret_cast<const char*>(data.data()), std::streamsize(data.size()));
}

static std::vector<uint8_t> ReadFile(const std::filesystem::path& p) {
  std::ifstream f(p, std::ios::binary);
  return std::vector<uint8_t>((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
}

int main(int argc, char** argv) {
  namespace fs = std::filesystem;
  const fs::path tmp_dir = fs::path(argv[1]);

  // 1. Switch parsing & precedence between R3HD_CROWN_CUTOUT (production) and R3HD_TEST_CROWN_BLEND (diagnostic).
  expect(!g6p127crown::Selected(nullptr), "Selected(nullptr) is false");
  expect(!g6p127crown::Selected(""), "Selected(empty) is false");
  expect(!g6p127crown::Selected("0"), "Selected(0) is false");
  expect(!g6p127crown::Selected("1"), "Selected(1) is false");
  expect(!g6p127crown::Selected("on"), "Selected(on) is false");
  expect(!g6p127crown::Selected("CUTOUT"), "Selected(CUTOUT) is false");
  expect(!g6p127crown::Selected("cutout "), "Selected(cutout ) is false");
  expect(g6p127crown::Selected("cutout"), "Selected(cutout) is true");

  expect(!g6p127crown::ResolveEnabled(nullptr, nullptr), "Resolve(null, null) == false");
  expect(!g6p127crown::ResolveEnabled("original", nullptr), "Resolve(original, null) == false");
  expect(!g6p127crown::ResolveEnabled("original", "cutout"), "Resolve(original, cutout) == false (prod wins)");
  expect(g6p127crown::ResolveEnabled("cutout", nullptr), "Resolve(cutout, null) == true");
  expect(g6p127crown::ResolveEnabled("cutout", "original"), "Resolve(cutout, original) == true (prod wins)");
  expect(g6p127crown::ResolveEnabled("cutout", "off"), "Resolve(cutout, off) == true (prod wins)");
  expect(g6p127crown::ResolveEnabled(nullptr, "cutout"), "Resolve(null, cutout) == true (diag fallback)");
  expect(g6p127crown::ResolveEnabled("", "cutout"), "Resolve(empty, cutout) == true (diag fallback)");
  expect(!g6p127crown::ResolveEnabled("bogus", "cutout"), "Resolve(bogus, cutout) == false (fail-closed prod)");
  expect(!g6p127crown::ResolveEnabled(nullptr, "CUTOUT"), "Resolve(null, CUTOUT) == false (case-sensitive)");
  expect(!g6p127crown::Enabled(), "Enabled() is false when env vars unset");

  // 2. Registry table completeness & exact filename lookup (no substring matching, no knaar_60.lvl).
  expect(g6p127crown::kCrownRecordCount == 10u, "kCrownRecordCount == 10");
  for (size_t i = 0; i < g6p127crown::kCrownRecordCount; ++i) {
    expect(g6p127crown::FindRecordIndex(g6p127crown::kCrownRecords[i].file) == i, "FindRecordIndex exact match");
  }
  expect(g6p127crown::FindRecordIndex("MENU_00.LVL") == 0u, "FindRecordIndex case-insensitive menu_00");
  expect(g6p127crown::FindRecordIndex("STAFF.LVL") == 9u, "FindRecordIndex case-insensitive staff");
  expect(g6p127crown::FindRecordIndex("knaar_60.lvl") == g6p127crown::kCrownRecordCount,
         "knaar_60.lvl (gum_crown) excluded");
  expect(g6p127crown::FindRecordIndex("menu_00.lvl.bak") == g6p127crown::kCrownRecordCount,
         "substring menu_00.lvl.bak excluded");
  expect(g6p127crown::FindRecordIndex("my_menu_00.lvl") == g6p127crown::kCrownRecordCount,
         "substring my_menu_00.lvl excluded");

  // 3. Build a synthetic 4096-byte menu_00.lvl fixture and matching RecordSpec.
  constexpr size_t kSynSize = 4096;
  constexpr uint64_t kSynRecOff = 0x400;
  constexpr size_t kSynRecLen = 0x80;
  constexpr size_t kSynBlendRel = 0x6C;
  constexpr uint64_t kSynBlendOff = kSynRecOff + kSynBlendRel;

  std::vector<uint8_t> syn_data(kSynSize, 0xA5u);
  WriteBE32(syn_data, 0, 0x000000D8u);
  WriteBE32(syn_data, size_t(kSynRecOff + 0x00), 0x4DDC43FFu);
  WriteBE32(syn_data, size_t(kSynRecOff + 0x68), 0x000047F4u);
  syn_data[size_t(kSynBlendOff)] = 0x03u;

  std::vector<uint8_t> syn_rec(syn_data.begin() + std::ptrdiff_t(kSynRecOff),
                               syn_data.begin() + std::ptrdiff_t(kSynRecOff + kSynRecLen));
  const uint64_t syn_stored_hash = g6p127crown::Fnv1a(syn_rec.data(), syn_rec.size());
  syn_rec[kSynBlendRel] = 0x08u;
  const uint64_t syn_patched_hash = g6p127crown::Fnv1a(syn_rec.data(), syn_rec.size());

  const g6p127crown::RecordSpec syn_spec = {
      "menu_00.lvl", kSynSize, 0ull, 0x000000D8u, kSynRecOff, kSynRecLen,
      0x00u, 0x4DDC43FFu, 0x68u, 0x000047F4u, kSynBlendRel, 0x03u, 0x08u,
      syn_stored_hash, syn_patched_hash,
  };

  const fs::path good_path = tmp_dir / "menu_00.lvl";
  WriteFile(good_path, syn_data);
  g6p127crown::state().log = &TestLog;

  // 4. Default switch absent (force=false): buffer completely unchanged.
  {
    g6p127crown::ResetForTest();
    std::vector<uint8_t> buf = syn_data;
    const size_t n = g6p127crown::AfterRead(good_path, 0, buf.data(), buf.size(), false, syn_spec);
    expect(n == 0, "default-off: returns 0");
    expect(buf == syn_data, "default-off: buffer unchanged");
  }

  // 5. Correct resource + enabled (force=true): ONLY the single target byte changes 0x03 -> 0x08.
  {
    g6p127crown::ResetForTest();
    g_logs.clear();
    std::vector<uint8_t> buf = syn_data;
    const size_t n = g6p127crown::AfterRead(good_path, 0, buf.data(), buf.size(), true, syn_spec);
    expect(n == 1, "good full read: returns 1");
    size_t diffs = 0;
    for (size_t i = 0; i < buf.size(); ++i) {
      if (buf[i] != syn_data[i]) ++diffs;
    }
    expect(diffs == 1 && buf[size_t(kSynBlendOff)] == 0x08u, "good full read: only blend byte changed 0x03->0x08");
    expect(ReadFile(good_path) == syn_data, "good full read: file on disk untouched");
    expect(g_logs.size() == 2, "good full read: logged validation and served_bytes");

    // Repeated application (idempotency): stable 0x08, no other byte touched.
    const size_t n2 = g6p127crown::AfterRead(good_path, 0, buf.data(), buf.size(), true, syn_spec);
    expect(n2 == 1 && buf[size_t(kSynBlendOff)] == 0x08u, "repeated application: idempotent 0x08");
    size_t diffs2 = 0;
    for (size_t i = 0; i < buf.size(); ++i) {
      if (buf[i] != syn_data[i]) ++diffs2;
    }
    expect(diffs2 == 1, "repeated application: still only 1 byte differs");
  }

  // 6. Partial / 1-byte / non-overlapping reads and case-insensitive filename.
  {
    const fs::path upper_path = tmp_dir / "MENU_00.LVL";
    WriteFile(upper_path, syn_data);
    g6p127crown::ResetForTest();
    uint8_t b = 0x03u;
    expect(g6p127crown::AfterRead(upper_path, kSynBlendOff, &b, 1, true, syn_spec) == 1 && b == 0x08u,
           "1-byte read + uppercase MENU_00.LVL: patched");
    std::vector<uint8_t> before(syn_data.begin(), syn_data.begin() + std::ptrdiff_t(kSynBlendOff));
    auto before_orig = before;
    expect(g6p127crown::AfterRead(upper_path, 0, before.data(), before.size(), true, syn_spec) == 0 &&
               before == before_orig,
           "non-overlapping read before target: untouched");
    std::vector<uint8_t> after(syn_data.begin() + std::ptrdiff_t(kSynBlendOff + 1), syn_data.end());
    auto after_orig = after;
    expect(g6p127crown::AfterRead(upper_path, kSynBlendOff + 1, after.data(), after.size(), true, syn_spec) == 0 &&
               after == after_orig,
           "non-overlapping read after target: untouched");
  }

  // 7. Wrong filename (wood_19.lvl, knaar_60.lvl): no patch.
  for (const char* bad_name : {"wood_19.lvl", "knaar_60.lvl", "fix.lvl"}) {
    const fs::path wrong_name = tmp_dir / bad_name;
    WriteFile(wrong_name, syn_data);
    g6p127crown::ResetForTest();
    std::vector<uint8_t> buf = syn_data;
    expect(g6p127crown::AfterRead(wrong_name, 0, buf.data(), buf.size(), true) == 0 && buf == syn_data,
           "unsupported bundle: no patch");
  }

  // 8. Wrong file size: no patch (kRefusedSize).
  {
    const fs::path bad_dir = tmp_dir / "bad_size";
    fs::create_directories(bad_dir);
    const fs::path p = bad_dir / "menu_00.lvl";
    auto d = syn_data;
    d.push_back(0x00u);
    WriteFile(p, d);
    g6p127crown::ResetForTest();
    expect(g6p127crown::ValidateFile(p, syn_spec) == g6p127crown::CheckState::kRefusedSize, "wrong size: kRefusedSize");
    auto buf = d;
    expect(g6p127crown::AfterRead(p, 0, buf.data(), buf.size(), true, syn_spec) == 0 && buf == d,
           "wrong size: no patch");
  }

  // 9. Wrong LVL header: no patch (kRefusedHeader).
  {
    const fs::path bad_dir = tmp_dir / "bad_hdr";
    fs::create_directories(bad_dir);
    const fs::path p = bad_dir / "menu_00.lvl";
    auto d = syn_data;
    WriteBE32(d, 0, 0x000000D9u);
    WriteFile(p, d);
    g6p127crown::ResetForTest();
    expect(g6p127crown::ValidateFile(p, syn_spec) == g6p127crown::CheckState::kRefusedHeader,
           "wrong header: kRefusedHeader");
    auto buf = d;
    expect(g6p127crown::AfterRead(p, 0, buf.data(), buf.size(), true, syn_spec) == 0 && buf == d,
           "wrong header: no patch");
  }

  // 10. Wrong material flags AND wrong tex record signature: no patch (kRefusedSignature).
  {
    const fs::path bad_dir = tmp_dir / "bad_flags";
    fs::create_directories(bad_dir);
    const fs::path p = bad_dir / "menu_00.lvl";
    auto d = syn_data;
    WriteBE32(d, size_t(kSynRecOff + 0x00), 0x4DDC47FFu);  // single-sided flags (like gum_crown)
    WriteFile(p, d);
    g6p127crown::ResetForTest();
    expect(g6p127crown::ValidateFile(p, syn_spec) == g6p127crown::CheckState::kRefusedSignature,
           "wrong flags signature: kRefusedSignature");
    auto buf = d;
    expect(g6p127crown::AfterRead(p, 0, buf.data(), buf.size(), true, syn_spec) == 0 && buf == d,
           "wrong flags signature: no patch");
  }
  {
    const fs::path bad_dir = tmp_dir / "bad_sig";
    fs::create_directories(bad_dir);
    const fs::path p = bad_dir / "menu_00.lvl";
    auto d = syn_data;
    WriteBE32(d, size_t(kSynRecOff + 0x68), 0x000047F5u);
    WriteFile(p, d);
    g6p127crown::ResetForTest();
    expect(g6p127crown::ValidateFile(p, syn_spec) == g6p127crown::CheckState::kRefusedSignature,
           "wrong tex signature: kRefusedSignature");
    auto buf = d;
    expect(g6p127crown::AfterRead(p, 0, buf.data(), buf.size(), true, syn_spec) == 0 && buf == d,
           "wrong tex signature: no patch");
  }

  // 11. Wrong original blend byte: no patch (kRefusedSourceByte).
  {
    const fs::path bad_dir = tmp_dir / "bad_byte";
    fs::create_directories(bad_dir);
    const fs::path p = bad_dir / "menu_00.lvl";
    auto d = syn_data;
    d[size_t(kSynBlendOff)] = 0x08u;
    WriteFile(p, d);
    g6p127crown::ResetForTest();
    expect(g6p127crown::ValidateFile(p, syn_spec) == g6p127crown::CheckState::kRefusedSourceByte,
           "wrong source byte: kRefusedSourceByte");
    auto buf = d;
    expect(g6p127crown::AfterRead(p, 0, buf.data(), buf.size(), true, syn_spec) == 0 && buf == d,
           "wrong source byte: no patch");
  }

  // 12. Altered surrounding material bytes: no patch (kRefusedStoredHash).
  {
    const fs::path bad_dir = tmp_dir / "bad_hash";
    fs::create_directories(bad_dir);
    const fs::path p = bad_dir / "menu_00.lvl";
    auto d = syn_data;
    d[size_t(kSynRecOff + 0x20)] ^= 0x01u;
    WriteFile(p, d);
    g6p127crown::ResetForTest();
    expect(g6p127crown::ValidateFile(p, syn_spec) == g6p127crown::CheckState::kRefusedStoredHash,
           "altered record byte: kRefusedStoredHash");
    auto buf = d;
    expect(g6p127crown::AfterRead(p, 0, buf.data(), buf.size(), true, syn_spec) == 0 && buf == d,
           "altered record byte: no patch");
  }

  // 13. Unexpected byte in caller buffer at target offset: fail-closed, no patch.
  {
    g6p127crown::ResetForTest();
    auto buf = syn_data;
    buf[size_t(kSynBlendOff)] = 0x05u;
    expect(g6p127crown::AfterRead(good_path, 0, buf.data(), buf.size(), true, syn_spec) == 0 &&
               buf[size_t(kSynBlendOff)] == 0x05u,
           "unexpected buffer byte: fail-closed");
  }

  // 14. M33 ordering: M33 applied after crown overlay wins on the same byte.
  {
    g6p127crown::ResetForTest();
    auto buf = syn_data;
    expect(g6p127crown::AfterRead(good_path, 0, buf.data(), buf.size(), true, syn_spec) == 1,
           "m33 ordering: crown overlay applied first");
    expect(buf[size_t(kSynBlendOff)] == 0x08u, "m33 ordering: crown wrote 0x08");
    buf[size_t(kSynBlendOff)] = 0x02u;
    expect(buf[size_t(kSynBlendOff)] == 0x02u, "m33 ordering: M33 mod wins");
  }

  // 15. Optional real GAMEDATAbin check (read-only) across ALL 10 bundles + knaar_60.lvl negative check.
  if (argc >= 3 && argv[2][0] != '\0') {
    const fs::path gamedata(argv[2]);
    g6p127crown::ResetForTest();
    for (size_t i = 0; i < g6p127crown::kCrownRecordCount; ++i) {
      const auto& spec = g6p127crown::kCrownRecords[i];
      std::string bundle(spec.file);
      bundle = bundle.substr(0, bundle.size() - 4);
      const fs::path real_path = gamedata / bundle / spec.file;
      expect(g6p127crown::ValidateFile(real_path, spec) == g6p127crown::CheckState::kApplied,
             spec.file);
      std::ifstream rf(real_path, std::ios::binary);
      std::vector<uint8_t> window(spec.record_size);
      rf.seekg(std::streamoff(spec.record_offset));
      rf.read(reinterpret_cast<char*>(window.data()), std::streamsize(window.size()));
      auto orig_window = window;
      const size_t rn = g6p127crown::AfterRead(real_path, spec.record_offset, window.data(), window.size(), true);
      expect(rn == 1 && window[spec.blend_rel_offset] == 0x08u, "real bundle: AfterRead patches 0x03 -> 0x08");
      size_t rdiffs = 0;
      for (size_t k = 0; k < window.size(); ++k) {
        if (window[k] != orig_window[k]) ++rdiffs;
      }
      expect(rdiffs == 1, "real bundle: strictly 1 byte modified in window");
    }
    // Negative check on real knaar_60.lvl (gum_crown.dds): untouched.
    const fs::path k60 = gamedata / "knaar_60" / "knaar_60.lvl";
    if (fs::exists(k60)) {
      std::vector<uint8_t> buf(256, 0x03u);
      auto orig = buf;
      expect(g6p127crown::AfterRead(k60, 0x2886A0ull, buf.data(), buf.size(), true) == 0 && buf == orig,
             "real knaar_60.lvl (gum_crown): untouched");
    }
  }

  std::printf("CPP_SUMMARY checks=%d fails=%d\n", g_checks, g_fails);
  return g_fails == 0 ? 0 : 1;
}
'''


def run_cpp_harness() -> None:
    with tempfile.TemporaryDirectory(prefix="g6p128_crown_test_") as td:
        td_path = Path(td)
        src = td_path / "harness.cpp"
        exe = td_path / "harness.exe"
        src.write_text(CPP_HARNESS, encoding="utf-8")

        compile_cmd = [
            "cmd", "/c", str(DEVENV),
            "clang++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
            "-D_CRT_SECURE_NO_WARNINGS",
            f"-I{ROOT / 'tools'}",
            str(src), "-o", str(exe),
        ]
        comp = subprocess.run(compile_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        check(comp.returncode == 0, f"C++20 harness compiles cleanly (rc={comp.returncode})")
        if comp.returncode != 0:
            print(comp.stdout)
            print(comp.stderr)
            return

        args = [str(exe), str(td_path)]
        if (GAMEDATA / "menu_00" / "menu_00.lvl").exists():
            args.append(str(GAMEDATA))
        else:
            global skipped
            skipped += 1
        run = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
        check(run.returncode == 0, f"C++20 harness passes (rc={run.returncode}: {run.stdout.strip()})")
        if run.returncode != 0:
            print(run.stdout)
            print(run.stderr)


def check_settings_and_launchers() -> None:
    reg = r3s.load_registry()
    entry = reg["settings"].get("crown_cutout")
    check(entry is not None, "registry contains crown_cutout")
    if entry:
        check(entry["group"] == "corrections" and entry["category"] == "hd_correction",
              "crown_cutout is hd_correction in corrections group")
        check(entry["values"] == ["original", "cutout"], "crown_cutout values are original/cutout")
        check(entry["vanilla"] == "original" and entry["hdplus"] == "cutout",
              "Vanilla=original and HD+=cutout")
        check(entry["launcher"] == "CrownCutout", "launcher param is CrownCutout")

    # Preset resolution: Vanilla, HD+, Custom on/off, existing correction independence, migration.
    van = r3s.resolve(reg, preset="vanilla")["values"]
    hdp = r3s.resolve(reg, preset="hdplus")["values"]
    check(van["crown_cutout"] == "original", "Vanilla resolves crown_cutout=original")
    check(hdp["crown_cutout"] == "cutout", "HD+ resolves crown_cutout=cutout")

    cust_off_doc = r3s.make_settings(reg, "custom", "hdplus", ["crown_cutout=original"])
    cust_off = r3s.resolve(reg, settings=cust_off_doc)["values"]
    check(cust_off["crown_cutout"] == "original" and cust_off["lockon_far_color"] == "restored"
          and cust_off["beam_color"] == "restored" and cust_off["texture_orient"] == "corrected",
          "Custom HD+ with crown_cutout=original keeps other HD+ corrections intact")

    cust_on_doc = r3s.make_settings(reg, "custom", "vanilla", ["crown_cutout=cutout"])
    cust_on = r3s.resolve(reg, settings=cust_on_doc)["values"]
    check(cust_on["crown_cutout"] == "cutout" and cust_on["lockon_far_color"] == "original"
          and cust_on["beam_color"] == "original" and cust_on["texture_orient"] == "original",
          "Custom Vanilla with crown_cutout=cutout keeps other Vanilla values intact")

    # Migration / persistence: pre-G6-P128 settings.json without crown_cutout.
    old_hdplus = {"schema": 3, "preset": "hdplus", "preferences": {"display": "fullscreen"}}
    old_vanilla = {"schema": 3, "preset": "vanilla", "preferences": {"display": "fullscreen"}}
    old_custom = {"schema": 3, "preset": "custom", "base": "hdplus",
                  "overrides": {"lockon_far_color": "original"}, "preferences": {}}
    check(r3s.resolve(reg, settings=old_hdplus)["values"]["crown_cutout"] == "cutout",
          "migration: existing HD+ settings.json adopts crown_cutout=cutout")
    check(r3s.resolve(reg, settings=old_vanilla)["values"]["crown_cutout"] == "original",
          "migration: existing Vanilla settings.json stays crown_cutout=original")
    m_cust = r3s.resolve(reg, settings=old_custom)["values"]
    check(m_cust["crown_cutout"] == "cutout" and m_cust["lockon_far_color"] == "original",
          "migration: existing Custom(hdplus) preserves prior overrides and inherits crown_cutout=cutout")

    # EN and TR UI strings present.
    ui = json.loads(read(UI_STRINGS))["strings"]
    lbl = entry["label"]
    hlp = entry["help"]
    check(lbl in ui and ui[lbl].get("en") == lbl and bool(ui[lbl].get("tr")),
          "ui_strings.json has EN and TR label for crown_cutout")
    check(hlp in ui and ui[hlp].get("en") == hlp and bool(ui[hlp].get("tr")),
          "ui_strings.json has EN and TR help for crown_cutout")

    # Windows play.ps1 & Linux r3hd_play.py wiring.
    play = read(PLAY_PS1)
    check("[ValidateSet('original', 'cutout')][string]$CrownCutout = 'original'" in play,
          "play.ps1 parameter contract defaults to original")
    for token in (
        "CrownCutout = 'crown_cutout'",
        "$env:R3HD_CROWN_CUTOUT = $CrownCutout",
        "$env:R3HD_CROWN_CUTOUT = $savedCrownCutout",
        "'R3HD_TEST_CROWN_BLEND'",
    ):
        check(token in play, f"play.ps1 contains {token}")
    check(play.count("crown_cutout = $CrownCutout") == 2, "play.ps1 launch.json and session.json record crown_cutout")

    linux = read(LINUX_PLAY)
    check('"CrownCutout": "crown_cutout"' in linux and '"R3HD_CROWN_CUTOUT": "CrownCutout"' in linux
          and '"R3HD_TEST_CROWN_BLEND"' in linux,
          "linux/r3hd_play.py maps CrownCutout / R3HD_CROWN_CUTOUT and scrubs R3HD_TEST_CROWN_BLEND")


def check_patch_idempotency() -> None:
    sample_hpf = (
        "#include <rex/r3hd_beam_color.h>\n"
        "#include <rex/r3hd_lockon_color.h>\n"
        "    if (r3hdlockon::Enabled()) {\n"
        "      r3hdlockon::AfterRead(p, off, buf, len);\n"
        "    }\n"
        "    // M33 (D-070): off unless R3HD_MODS_PLAN names a verified plan; listed ranges of listed files only.\n"
        "    if (m33mods::Enabled()) {\n"
        "      m33mods::AfterRead(p, off, buf, len);\n"
        "    }\n"
    )
    sample_cp = (
        "#include <rex/r3hd_beam_color.h>\n"
        "#include <rex/r3hd_lockon_color.h>\n"
        '  REXGPU_INFO("R3HD beam_color={}", r3hdbeam::Enabled() ? "restored" : "original");\n'
        '  REXGPU_INFO("R3HD lockon_color={}", r3hdlockon::Enabled() ? "restored" : "original");\n'
    )
    patch_src = read(PATCH)
    check('#include <rex/g6p127_crown_blend.h>' in patch_src, "patch installs and includes g6p127_crown_blend.h")
    check('g6p127crown::Enabled()' in patch_src and 'g6p127crown::AfterRead(' in patch_src,
          "patch gates AfterRead behind Enabled()")
    check('R3HD_MODS_PLAN' in patch_src, "patch anchors before M33 mods")

    inc_old = '#include <rex/r3hd_lockon_color.h>\n'
    inc_new = '#include <rex/r3hd_lockon_color.h>\n#include <rex/g6p127_crown_blend.h>\n'
    m33_anchor = '    // M33 (D-070): off unless R3HD_MODS_PLAN names a verified plan; listed ranges of listed files only.\n'
    block = (
        '    // G6-P127 / G6-P128 (D-362, D-363): HD+ Grand Minimus crown cutout (0x03 -> 0x08) across all 10\n'
        '    // verified teensy_cour.dds .lvl bundles; off unless R3HD_CROWN_CUTOUT=cutout (or diagnostic fallback\n'
        '    // R3HD_TEST_CROWN_BLEND=cutout when R3HD_CROWN_CUTOUT is unset). Before M33 so mods win.\n'
        '    if (g6p127crown::Enabled()) {\n'
        '      g6p127crown::state().log = &M26Log;\n'
        '      g6p127crown::AfterRead(static_cast<HostPathEntry*>(entry())->host_path(), byte_offset, buffer.data(),\n'
        '                             out_bytes_read ? *out_bytes_read : buffer.size());\n'
        '    }\n'
        + m33_anchor
    )
    hpf1 = sample_hpf.replace(inc_old, inc_new, 1).replace(m33_anchor, block, 1)
    hpf2 = hpf1 if inc_new in hpf1 else hpf1.replace(inc_old, inc_new, 1)
    hpf2 = hpf2 if block in hpf2 else hpf2.replace(m33_anchor, block, 1)
    check(hpf1 == hpf2 and hpf1.count('g6p127crown::AfterRead(') == 1, "host_path_file.cpp patch is idempotent")
    check(hpf1.index('r3hdlockon::AfterRead(') < hpf1.index('g6p127crown::AfterRead(') < hpf1.index('m33mods::AfterRead('),
          "host_path_file.cpp ordering: lockon < g6p127crown < m33mods")

    cp_old = '  REXGPU_INFO("R3HD lockon_color={}", r3hdlockon::Enabled() ? "restored" : "original");\n'
    cp_new = cp_old + '  REXGPU_INFO("R3HD crown_cutout={}", g6p127crown::Enabled() ? "cutout" : "original");\n'
    cp1 = sample_cp.replace(inc_old, inc_new, 1).replace(cp_old, cp_new, 1)
    cp2 = cp1 if cp_new in cp1 else cp1.replace(cp_old, cp_new, 1)
    check(cp1 == cp2 and cp1.count('R3HD crown_cutout=') == 1, "command_processor.cpp patch is idempotent")


def main() -> int:
    hdr = read(HEADER)
    check('R3HD_CROWN_CUTOUT' in hdr and 'R3HD_TEST_CROWN_BLEND' in hdr and 'ResolveEnabled(' in hdr,
          "header implements R3HD_CROWN_CUTOUT with R3HD_TEST_CROWN_BLEND fallback")
    for bundle in VERIFIED_BUNDLES:
        check(f'"{bundle}.lvl"' in hdr, f"header includes verified bundle {bundle}.lvl")
    check('"knaar_60.lvl"' not in hdr and 'gum_crown' not in hdr.lower().replace('gum_crown.dds', ''),
          "header does not target knaar_60.lvl")
    check(not re.search(r'\{(?:\s*0x[0-9A-Fa-f]{2},){16}', hdr),
          "header contains no proprietary byte arrays")

    check_settings_and_launchers()

    bat = read(BAT)
    check(
        bat.index("g6p109_audio_client_lifetime_patch.py")
        < bat.index("g6p127_crown_blend_patch.py")
        < bat.index("cmake -S external"),
        "build_milestone8.bat runs g6p127_crown_blend_patch.py last before cmake configure",
    )
    check(
        bat.index("g6p127_crown_blend_regression.py") < bat.index("echo M8_BUILD_OK"),
        "build_milestone8.bat runs g6p127_crown_blend_regression.py before M8_BUILD_OK",
    )

    check_patch_idempotency()

    # If the SDK has already been patched by a build replay, verify live SDK patch state.
    hpf = SDK / "src" / "filesystem" / "devices" / "host_path_file.cpp"
    cp = SDK / "src" / "graphics" / "d3d12" / "command_processor.cpp"
    if hpf.exists() and "g6p127crown::" in read(hpf):
        hpf_txt = read(hpf)
        i26 = hpf_txt.index("m26tex::AfterRead(")
        ib = hpf_txt.index("r3hdbeam::AfterRead(")
        il = hpf_txt.index("r3hdlockon::AfterRead(")
        ic = hpf_txt.index("g6p127crown::AfterRead(")
        i33 = hpf_txt.index("m33mods::AfterRead(")
        check(i26 < ib < il < ic < i33, "patched SDK: M26 < beam < lockon < g6p127crown < M33")
        check(hpf_txt.count("g6p127crown::AfterRead(") == 1, "patched SDK: exactly 1 g6p127crown::AfterRead call")
        cp_txt = read(cp)
        has_mode = ('REXGPU_INFO("R3HD crown_cutout={}"' in cp_txt or 'REXGPU_INFO("G6P127 crown_blend={}"' in cp_txt)
        check(has_mode, "patched SDK: crown mode log line present")
    else:
        global skipped
        skipped += 1

    run_cpp_harness()

    status = "PASS" if failures == 0 else "FAIL"
    print(f"G6P127_CROWN_BLEND_REGRESSION {status} checks={checks} failures={failures} skipped={skipped}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
