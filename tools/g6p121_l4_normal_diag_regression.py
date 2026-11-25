#!/usr/bin/env python3
"""G6-P121 (D-356, E-602) offline regression for the opt-in L4 `1t_d_lighting` normal-sign diagnostic.

Verifies without launching the game or modifying `external/rexglue-sdk`:
  1. Static microcode & Xenos ALU bitfield invariants of `kL4NormalNegateEdits` in `tools/uvs_lit_scroll.h`.
  2. Real C++20 compilation and execution of `tools/uvs_lit_scroll.h` testing all four
     `(lit_uv_scroll x l4_normal_sign)` configurations (neither, UVS-only, L4-only, both), sequential vs.
     composed equivalence, fail-closed rejection, env-var parsing, and opaque-PS filtering.
  3. Real dumped `D64D176416571592` microcode check when retained locally under `private/` (skipped cleanly
     in public/clean-tree environments where `private/` is absent).
  4. Patch-script composition, Vulkan-parity region containment, temp-copy idempotency, and Vanilla/HD+/Custom
     default preservation (`R3HD_TEST_LIT_NORMAL_SIGN` absent from `registry.json` and `play.ps1`).
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "tools" / "uvs_lit_scroll.h"
PATCH = ROOT / "tools" / "uvs_runtime_patch.py"
REGISTRY = ROOT / "config" / "settings" / "registry.json"
PLAY_PS1 = ROOT / "tools" / "play.ps1"
DEVENV = ROOT / "tools" / "devenv.bat"
DUMP_UCODE = ROOT / "private" / "work" / "m6_runs" / "hidden_bounded" / "shaders" / "shader_D64D176416571592.ucode.bin.vert"

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
#include <cstdlib>
#include <fstream>
#include <vector>
#include "uvs_lit_scroll.h"

static int g_checks = 0;
static int g_fails = 0;
static void expect(bool cond, const char* msg) {
  ++g_checks;
  if (!cond) {
    ++g_fails;
    std::printf("CPP_FAIL %s\n", msg);
  }
}

static std::vector<uint32_t> make_synthetic_ucode() {
  std::vector<uint32_t> u(120, 0x13579BDFu);
  for (size_t i = 0; i < uvslit::kVertexPlan.edit_count; ++i)
    u[uvslit::kVertexPlan.edits[i].dword] = uvslit::kVertexPlan.edits[i].expect;
  for (size_t i = 0; i < uvslit::kL4NormalNegatePlan.edit_count; ++i)
    u[uvslit::kL4NormalNegatePlan.edits[i].dword] = uvslit::kL4NormalNegatePlan.edits[i].expect;
  return u;
}

static std::vector<uint32_t> swap_all(const std::vector<uint32_t>& v) {
  std::vector<uint32_t> out(v);
  for (uint32_t& x : out) x = uvslit::ByteSwap(x);
  return out;
}

static void verify_ucode_suite(const std::vector<uint32_t>& orig_host, const char* tag) {
  // 1. Neither active
  auto c00 = uvslit::CorrectedComposed(orig_host, false, false);
  expect(c00.empty(), "cfg00: neither returns empty (draw original)");

  // 2. UVS only: bit-identical to legacy uvslit::Corrected(kVertexPlan)
  auto c10_legacy = uvslit::Corrected(orig_host, uvslit::kVertexPlan);
  auto c10_comp = uvslit::CorrectedComposed(orig_host, true, false);
  expect(c10_legacy.size() == 120 && c10_legacy == c10_comp, "cfg10: UVS-only matches legacy bit-for-bit");

  // 3. L4 only: exactly 8 dwords change, each by XOR 0x04000000
  auto c01_direct = uvslit::Corrected(orig_host, uvslit::kL4NormalNegatePlan);
  auto c01_comp = uvslit::CorrectedComposed(orig_host, false, true);
  expect(c01_direct.size() == 120 && c01_direct == c01_comp, "cfg01: L4-only direct == composed");
  auto c01_host = swap_all(c01_direct);
  int diff_count = 0;
  bool only_neg_bit = true;
  for (size_t i = 0; i < 120; ++i) {
    if (c01_host[i] != orig_host[i]) {
      ++diff_count;
      if ((c01_host[i] ^ orig_host[i]) != uvslit::kAluSrc1NegateBit) only_neg_bit = false;
    }
  }
  expect(diff_count == 8 && only_neg_bit, "cfg01: exactly 8 dwords flip only bit 26");
  expect(c01_host.size() == 120 && c01_host[77] == orig_host[77], "cfg01: instr 25 (UVS dword 77) untouched");

  // 4. Both active: sequential (UVS -> L4) == composed (true, true) == (L4 -> UVS)
  auto c11_comp = uvslit::CorrectedComposed(orig_host, true, true);
  auto c11_seq_uvs_then_l4 = uvslit::Corrected(swap_all(c10_legacy), uvslit::kL4NormalNegatePlan);
  auto c11_seq_l4_then_uvs = uvslit::Corrected(c01_host, uvslit::kVertexPlan);
  expect(c11_comp.size() == 120, "cfg11: composed size 120");
  expect(c11_comp == c11_seq_uvs_then_l4, "cfg11: sequential UVS->L4 matches composed bit-for-bit");
  expect(c11_comp == c11_seq_l4_then_uvs, "cfg11: sequential L4->UVS matches composed bit-for-bit");

  // All 4 outputs distinct
  auto orig_be = swap_all(orig_host);
  expect(orig_be != c10_comp && orig_be != c01_comp && orig_be != c11_comp &&
             c10_comp != c01_comp && c10_comp != c11_comp && c01_comp != c11_comp,
         "all 4 configs produce distinct microcode");

  // Fail-closed: wrong lengths
  auto short_u = orig_host;
  short_u.pop_back();
  expect(uvslit::Corrected(short_u, uvslit::kL4NormalNegatePlan).empty(), "fail-closed: len 119");
  auto long_u = orig_host;
  long_u.push_back(0);
  expect(uvslit::Corrected(long_u, uvslit::kL4NormalNegatePlan).empty(), "fail-closed: len 121");

  // Fail-closed: corrupted L4 dword
  auto bad_l4 = orig_host;
  bad_l4[64] ^= 1u;
  expect(uvslit::Corrected(bad_l4, uvslit::kL4NormalNegatePlan).empty(), "fail-closed: corrupt L4 dword 64");
  expect(uvslit::CorrectedComposed(bad_l4, true, true).empty(), "fail-closed: composed rejects corrupt L4 dword");
  expect(!uvslit::CorrectedComposed(bad_l4, true, false).empty(), "UVS-only ignores unrelated L4 dword");

  // Fail-closed: corrupted UVS dword
  auto bad_uvs = orig_host;
  bad_uvs[77] ^= 1u;
  expect(uvslit::CorrectedComposed(bad_uvs, true, true).empty(), "fail-closed: composed rejects corrupt UVS dword");
  expect(!uvslit::CorrectedComposed(bad_uvs, false, true).empty(), "L4-only ignores unrelated UVS dword");

  std::printf("CPP_SUITE %s OK\n", tag);
}

int main(int argc, char** argv) {
  // Mode parser & PS filter checks
  expect(uvslit::ParseTestNormalMode(nullptr) == uvslit::L4NormalMode::kOff, "mode nullptr -> kOff");
  expect(uvslit::ParseTestNormalMode("") == uvslit::L4NormalMode::kOff, "mode empty -> kOff");
  expect(uvslit::ParseTestNormalMode("original") == uvslit::L4NormalMode::kOff, "mode original -> kOff");
  expect(uvslit::ParseTestNormalMode("applied") == uvslit::L4NormalMode::kOff, "mode applied -> kOff");
  expect(uvslit::ParseTestNormalMode("1") == uvslit::L4NormalMode::kOff, "mode 1 -> kOff");
  expect(uvslit::ParseTestNormalMode("negate") == uvslit::L4NormalMode::kAll, "mode negate -> kAll");
  expect(uvslit::ParseTestNormalMode("negate_opaque") == uvslit::L4NormalMode::kOpaquePsOnly,
         "mode negate_opaque -> kOpaquePsOnly");

  constexpr uint64_t kPsOpaque = 0xA45DEA01F464F217ull;
  constexpr uint64_t kPsBlended = 0x8A9216DD8631A0C9ull;
  constexpr uint64_t kPsNoDiffuse = 0x02832570BD05BDDCull;
  expect(!uvslit::TestNormalMatches(uvslit::L4NormalMode::kOff, kPsOpaque), "kOff rejects opaque PS");
  expect(uvslit::TestNormalMatches(uvslit::L4NormalMode::kAll, kPsOpaque), "kAll matches opaque PS");
  expect(uvslit::TestNormalMatches(uvslit::L4NormalMode::kAll, kPsBlended), "kAll matches blended PS");
  expect(uvslit::TestNormalMatches(uvslit::L4NormalMode::kAll, kPsNoDiffuse), "kAll matches no-diffuse PS");
  expect(uvslit::TestNormalMatches(uvslit::L4NormalMode::kOpaquePsOnly, kPsOpaque), "kOpaquePsOnly matches opaque PS");
  expect(!uvslit::TestNormalMatches(uvslit::L4NormalMode::kOpaquePsOnly, kPsBlended), "kOpaquePsOnly skips blended PS");
  expect(!uvslit::TestNormalMatches(uvslit::L4NormalMode::kOpaquePsOnly, kPsNoDiffuse), "kOpaquePsOnly skips no-diffuse PS");

  verify_ucode_suite(make_synthetic_ucode(), "synthetic");

  if (argc > 1) {
    std::ifstream f(argv[1], std::ios::binary);
    expect(bool(f), "open real ucode dump");
    if (f) {
      std::vector<uint32_t> u(120);
      f.read(reinterpret_cast<char*>(u.data()), 120 * sizeof(uint32_t));
      expect(f.gcount() == 120 * 4, "real ucode dump is 480 bytes");
      verify_ucode_suite(u, "real_dump");
    }
  }

  std::printf("CPP_RESULT checks=%d failures=%d\n", g_checks, g_fails);
  return g_fails ? 1 : 0;
}
'''


def main() -> int:
    global skipped
    hdr = read(HEADER)
    check("kL4NormalNegateEdits[]" in hdr, "header defines kL4NormalNegateEdits")
    check("kL4NormalNegatePlan = {120, kL4NormalNegateEdits" in hdr, "L4 plan requires 120-dword microcode")
    check('std::getenv("R3HD_TEST_LIT_NORMAL_SIGN")' in hdr, "L4 diagnostic keyed solely to private env var")
    check("kOpaquePropPixelShaderHash = 0xA45DEA01F464F217ull;" in hdr, "opaque PS hash matches census")

    block = hdr.split("kL4NormalNegateEdits[] = {", 1)[1].split("};", 1)[0]
    edits = [tuple(int(x, 0) for x in m) for m in re.findall(r"\{(\d+), (0x[0-9A-Fa-f]+)u, (0x[0-9A-Fa-f]+)u\}", block)]
    check(len(edits) == 24, "L4 plan covers all 24 dwords of instructions 16..23")
    check([e[0] for e in edits] == list(range(48, 72)), "L4 dwords are exactly 48..71 (disjoint from UVS 75..77)")

    changed = [e for e in edits if e[1] != e[2]]
    check([e[0] for e in changed] == [49, 52, 55, 58, 61, 64, 67, 70], "exactly 8 dword-1 slots change")
    check(all((e[2] ^ e[1]) == 0x04000000 and (e[1] & 0x04000000) == 0 for e in changed),
          "every changed dword sets only src1_reg_negate (bit 26 = 0x04000000)")

    # Verify Xenos ALU instruction bitfields for all 8 dp3 instructions
    expected_consts = [44, 45, 46, 47, 52, 53, 54, 55]
    for idx, c_reg in enumerate(expected_consts):
        d0, d1_old, d1_new, d2 = edits[idx * 3][1], edits[idx * 3 + 1][1], edits[idx * 3 + 1][2], edits[idx * 3 + 2][1]
        vopc = (d2 >> 24) & 0x1F
        s1_sel, s1_reg, s1_swiz = (d2 >> 31) & 1, (d2 >> 16) & 0xFF, (d1_old >> 16) & 0xFF
        s2_sel, s2_reg, s2_swiz = (d2 >> 30) & 1, (d2 >> 8) & 0xFF, (d1_old >> 8) & 0xFF
        check(vopc == 16 and s1_sel == 1 and s1_reg == 4 and s1_swiz == 0xBE
              and s2_sel == 0 and s2_reg == c_reg and s2_swiz == 0xBE
              and ((d1_old >> 26) & 1) == 0 and ((d1_new >> 26) & 1) == 1
              and (d0 & 0x3F) in (1, 2),
              f"instr {16 + idx}: dp3 r{d0 & 0x3F}, (-)r4.zxyy, c{c_reg}.zxyy")

    # Patch & Vulkan-parity region checks
    patch_txt = read(PATCH)
    check("uvslit::TestNormalMode()" in patch_txt and "uvslit::kL4NormalNegatePlan" in patch_txt,
          "uvs_runtime_patch.py wires L4 diagnostic sequentially after UVS")
    check("L4_DIAG lit_normal_sign" in patch_txt, "L4 diagnostic logs once when active")
    check("R3HD_TEST_LIT_NORMAL_SIGN" not in read(REGISTRY), "no Settings registry key added for L4 diagnostic")
    check("R3HD_TEST_LIT_NORMAL_SIGN" not in read(PLAY_PS1), "no play.ps1 preset wiring added for L4 diagnostic")

    # Temp-copy idempotency check for tools/uvs_runtime_patch.py (never touches external/rexglue-sdk)
    sys.path.insert(0, str(ROOT / "tools"))
    import uvs_runtime_patch as UP  # noqa: E402
    sample_cp = (
        '#include <rex/m23_water_layers.h>\n'
        'void init() {\n'
        '  REXGPU_INFO("M23 layer_coords={}", m23water::Enabled() ? "separate" : "original");\n'
        '}\n'
        'void issue() {\n'
        + UP.M23_FIRST +
        '  // M22: one-frame draw-state trace\n'
        '}\n'
    )
    def apply_edits(text: str) -> str:
        for marker, (before, after) in UP.EDITS:
            if marker not in text:
                assert text.count(before) == 1
                text = text.replace(before, after, 1)
        return text
    once = apply_edits(sample_cp)
    twice = apply_edits(once)
    check(once == twice, "uvs_runtime_patch.py EDITS are idempotent on temp copy")
    check("uvslit::TestNormalMode()" in once and once.count("L4_DIAG lit_normal_sign") == 1,
          "patched temp copy contains L4 diagnostic block exactly once")
    check(once.index("L4_DIAG lit_normal_sign") < once.index(UP.M23_FIRST),
          "L4 diagnostic sits inside UVS/M23 Vulkan-parity region")

    # Compile and execute C++20 unit harness against tools/uvs_lit_scroll.h
    with tempfile.TemporaryDirectory(prefix="g6p121_l4_") as td:
        td_path = Path(td)
        src = td_path / "test_l4.cpp"
        exe = td_path / "test_l4.exe"
        src.write_text(CPP_HARNESS, encoding="utf-8")
        if DEVENV.exists():
            bat = td_path / "compile.bat"
            bat.write_text(
                f'@echo off\r\ncall "{DEVENV}" >nul\r\n'
                f'clang++ -std=c++20 -D_CRT_SECURE_NO_WARNINGS -Wall -Wextra -Werror -I"{ROOT / "tools"}" "{src}" -o "{exe}"\r\n',
                encoding="utf-8",
            )
            comp = subprocess.run(["cmd", "/c", str(bat)], capture_output=True, text=True)
        else:
            comp = subprocess.run(["clang++", "-std=c++20", "-D_CRT_SECURE_NO_WARNINGS", "-Wall", "-Wextra", "-Werror",
                                   f"-I{ROOT / 'tools'}", str(src), "-o", str(exe)], capture_output=True, text=True)
        check(comp.returncode == 0, f"C++20 compile of uvs_lit_scroll.h harness (rc={comp.returncode})")
        if comp.returncode != 0:
            print(comp.stdout)
            print(comp.stderr)
        else:
            run_args = [str(exe)]
            if DUMP_UCODE.exists():
                run_args.append(str(DUMP_UCODE))
            else:
                skipped += 1
                print("note: private D64D176416571592 ucode dump absent; real-dump subsuite skipped")
            run = subprocess.run(run_args, capture_output=True, text=True)
            check(run.returncode == 0 and "CPP_RESULT" in run.stdout and "failures=0" in run.stdout,
                  f"C++20 4-config & fail-closed harness passed (rc={run.returncode})")
            if run.returncode != 0:
                print(run.stdout)
                print(run.stderr)
            else:
                for ln in run.stdout.splitlines():
                    if ln.startswith(("CPP_SUITE", "CPP_RESULT")):
                        print(" ", ln)

    print(f"G6P121_L4_DIAG_REGRESSION {'PASS' if failures == 0 else 'FAIL'} checks={checks} failures={failures} skipped={skipped}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
