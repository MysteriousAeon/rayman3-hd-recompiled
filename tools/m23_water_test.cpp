// M23 (D-052): the two-layer surface correction's microcode edit, deterministic checks. Host-only; the buffers
// are synthetic (only the dwords named in the edit tables carry the title's values).
#include "m23_water_layers.h"
#include <cstdio>

static int checks = 0, failures = 0;
static void Check(bool ok, const char* what) {
  ++checks;
  if (!ok) {
    ++failures;
    std::printf("FAIL %s\n", what);
  }
}

static std::vector<uint32_t> Synthetic(const m23water::Plan& plan) {
  std::vector<uint32_t> ucode(plan.dword_count);
  for (size_t i = 0; i < ucode.size(); ++i) ucode[i] = 0x51000000u + uint32_t(i) * 0x01010101u;
  for (size_t i = 0; i < plan.edit_count; ++i) ucode[plan.edits[i].dword] = plan.edits[i].expect;
  return ucode;
}

static void PlanChecks(const m23water::Plan& plan, const char* name) {
  using namespace m23water;
  const std::vector<uint32_t> original = Synthetic(plan);
  const std::vector<uint32_t> corrected = Corrected(original, plan);
  Check(corrected.size() == original.size(), name);
  size_t changed = 0, edited_right = 0;
  for (size_t i = 0; i < corrected.size(); ++i) {
    const uint32_t host = ByteSwap(corrected[i]);
    if (host != original[i]) ++changed;
    for (size_t k = 0; k < plan.edit_count; ++k)
      if (plan.edits[k].dword == i && host == plan.edits[k].value) ++edited_right;
  }
  Check(changed == plan.edit_count, "only the listed dwords change");
  Check(edited_right == plan.edit_count, "every listed dword has its corrected value, big-endian out");

  // Anything that is not exactly the expected microcode is left alone.
  std::vector<uint32_t> shorter(original.begin(), original.end() - 3);
  Check(Corrected(shorter, plan).empty(), "shorter microcode refused");
  std::vector<uint32_t> longer(original);
  longer.push_back(0);
  Check(Corrected(longer, plan).empty(), "longer microcode refused");
  for (size_t k = 0; k < plan.edit_count; ++k) {
    std::vector<uint32_t> other(original);
    other[plan.edits[k].dword] ^= 0x00000020u;
    Check(Corrected(other, plan).empty(), "microcode with another value at an edited place refused");
  }
  // Applying the edit to its own (host-order) result is refused too: no double application.
  std::vector<uint32_t> again(corrected);
  for (uint32_t& v : again) v = ByteSwap(v);
  Check(Corrected(again, plan).empty(), "already corrected microcode refused");
}

int main() {
  using namespace m23water;
  Check(!Selected(nullptr) && !Selected("") && !Selected("original") && !Selected("1") && !Selected("Separate"),
        "the title's behaviour unless the value is exactly 'separate'");
  Check(Selected("separate"), "'separate' selects the correction");
  // D-054: the current variable decides whenever it is set; the first name counts only without it.
  Check(Selected(Value("separate", nullptr)) && Selected(Value(nullptr, "separate")), "either name selects it");
  Check(!Selected(Value("original", "separate")) && !Selected(Value("", "separate")),
        "a set current variable is not overridden by the first name");
  Check(Selected(Value("separate", "original")) && !Selected(Value(nullptr, nullptr)) &&
            !Selected(Value(nullptr, "original")),
        "current name first; nothing set is the title's behaviour");
  Check(ByteSwap(0x11223344u) == 0x44332211u && ByteSwap(ByteSwap(0xC8038003u)) == 0xC8038003u, "byte swap");

  PlanChecks(kVertexPlan, "vertex plan accepted");
  PlanChecks(kPixelPlan, "pixel plan accepted");

  // Field-level meaning of the edits (ALU and fetch instruction layouts of the pinned SDK's ucode.h).
  const uint32_t v0 = kVertexEdits[0].value, v1 = kVertexEdits[1].value, v2 = kVertexEdits[2].value;
  Check((v0 & 0x3F) == 3 && ((v0 >> 15) & 1) == 1, "vector destination is export 3 (interpolator 3)");
  Check(((v0 >> 16) & 0xF) == 0x3 && ((v0 >> 20) & 0xF) == 0, "write mask xy, no scalar write");
  Check(((v2 >> 24) & 0x1F) == 0, "vector operation add");
  Check(((v2 >> 16) & 0xFF) == 3 && ((v2 >> 31) & 1) == 1, "first operand is temporary register r3");
  Check(((v2 >> 8) & 0xFF) == 11 && ((v2 >> 30) & 1) == 0, "second operand is constant c11");
  Check(((v1 >> 16) & 0xFF) == 0xB0 && ((v1 >> 8) & 0xFF) == 0xB0 && (v1 >> 24) == 0,
        "both operands swizzled xyyy, nothing negated or predicated");
  const uint32_t p_old = kPixelEdits[0].expect, p_new = kPixelEdits[0].value;
  Check((p_old & 0x1F) == 1 && (p_new & 0x1F) == 1, "texture fetch before and after");
  Check(((p_old >> 5) & 0x3F) == 0 && ((p_new >> 5) & 0x3F) == 3, "coordinate register r0 -> r3");
  Check((p_old & ~0x7E0u) == (p_new & ~0x7E0u), "destination, sampler index and swizzle unchanged");
  Check(((p_new >> 20) & 0x1F) == 1 && ((p_new >> 12) & 0x3F) == 6, "second sampler, destination r6");
  Check(kVertexShaderHash != kPixelShaderHash, "distinct shaders");

  std::printf("M23_WATER_TEST %s checks=%d failures=%d\n", failures ? "FAIL" : "PASS", checks, failures);
  return failures ? 1 : 0;
}
