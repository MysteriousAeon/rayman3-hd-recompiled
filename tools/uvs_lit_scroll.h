// Lit UV scroll (E-353, D-157, experimental): optional texture-scroll correction for the title's one-layer lit
// vertex shader `1t_d_lighting`. Installed as include/rex/uvs_lit_scroll.h by tools/uvs_runtime_patch.py and used by
// the D3D12 command processor only.
//
// What the title does (RE_NOTES "Fist charge trail"): every one-layer vertex shader of the title adds the UV
// offset the engine writes to vertex constant c10.xy (`add oT0, v2, c10` in the original Xbox sources) except
// `1t_d_lighting`, which passes the coordinates through (`mov oT0, vUV`; the HD HLSL never reads `matUV`). The
// fist-charge trail is drawn with it: the engine scrolls the trail's fire gradient with the charge (c10.y up to
// about 0.49) and the shader ignores it, so the ribbon keeps sampling the gradient's black top. That is the Xbox
// 360 HD release's own behaviour (class B), so it stays the default.
//
// With R3HD_LIT_UV_SCROLL=applied the host draws that vertex shader from an edited copy of the title's microcode:
// instruction 25, the export of coordinates and fog factor `max o0.xyz_, r3.xyzz, r3.xyzz`, becomes
// `add o0.xyz_, r3.xyzz, c10.xyzz`. Only the operation and the second operand change (dword 77); the encoding is
// the one of the M23 edit (`add ..., c11` = A0030B00) with constant 10. In every traced draw of this shader other
// than the trail c10 is (0, 0, 0, 0), so those draws compute the same coordinates and fog factor (E-353).
// Nothing else changes: no guest memory, no register, no pixel shader, no texture. The edit is applied only to
// microcode of the expected length whose dwords at the edited places have the expected values; otherwise the
// shader is drawn as issued.
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <vector>

namespace uvslit {
constexpr uint64_t kVertexShaderHash = 0xD64D176416571592ull;  // `1t_d_lighting`, the copy the title binds

struct Edit {
  uint32_t dword;   // index into the microcode (instruction index * 3 + word)
  uint32_t expect;  // the title's value (host byte order)
  uint32_t value;   // the corrected value
};
struct Plan {
  size_t dword_count;
  const Edit* edits;
  size_t edit_count;
};

// Instruction 25, `max o0.xyz_, r3.xyzz, r3.xyzz` -> `add o0.xyz_, r3.xyzz, c10.xyzz`. Dwords 75 (`C8078000`,
// export o0, mask xyz) and 76 (`00C0C000`, swizzles xyzz) are checked, not changed.
constexpr Edit kVertexEdits[] = {
    {75, 0xC8078000u, 0xC8078000u}, {76, 0x00C0C000u, 0x00C0C000u}, {77, 0xE2030300u, 0xA0030A00u}};
constexpr Plan kVertexPlan = {120, kVertexEdits, sizeof(kVertexEdits) / sizeof(Edit)};

// "applied" selects the correction; anything else, or no variable, is the title's own behaviour.
inline bool Selected(const char* value) { return value && std::strcmp(value, "applied") == 0; }
inline bool Enabled() {
  static const bool on = Selected(std::getenv("R3HD_LIT_UV_SCROLL"));
  return on;
}

constexpr uint32_t ByteSwap(uint32_t v) {
  return (v >> 24) | ((v >> 8) & 0x0000FF00u) | ((v << 8) & 0x00FF0000u) | (v << 24);
}

// Edited copy of `ucode` (host byte order in, guest big-endian order out, which is what the shader loader
// takes). Empty when the microcode is not exactly the expected one.
inline std::vector<uint32_t> Corrected(const std::vector<uint32_t>& ucode, const Plan& plan) {
  if (ucode.size() != plan.dword_count) return {};
  for (size_t i = 0; i < plan.edit_count; ++i)
    if (plan.edits[i].dword >= ucode.size() || ucode[plan.edits[i].dword] != plan.edits[i].expect) return {};
  std::vector<uint32_t> out(ucode);
  for (size_t i = 0; i < plan.edit_count; ++i) out[plan.edits[i].dword] = plan.edits[i].value;
  for (uint32_t& v : out) v = ByteSwap(v);
  return out;
}

// G6-P121 (D-356, diagnostic-only, off by default, outside Settings and presets): optional normal-sign negation
// for `1t_d_lighting` (`D64D176416571592`). Sets `src1_reg_negate` (bit 26 = 0x04000000u in AluInstruction dword 1)
// on the eight directional-light `dp3` instructions (instructions 16..23, dwords 48..71), mirroring the title's
// sibling skinned lighting shaders (`9C1563CAC62D2F0F` instr 50..57). Completely disjoint from `kVertexEdits`
// (instruction 25, dwords 75..77), so all four (lit_uv_scroll x l4_normal_sign) configurations compose cleanly.
// Controlled solely by private test env var `R3HD_TEST_LIT_NORMAL_SIGN`:
//   - unset / anything else: kOff (Vanilla / HD+ / Custom bit-identical)
//   - "negate":              kAll (every D64D176416571592 draw)
//   - "negate_opaque":       kOpaquePsOnly (only when paired with opaque-prop PS A45DEA01F464F217)
constexpr uint64_t kOpaquePropPixelShaderHash = 0xA45DEA01F464F217ull;
constexpr uint32_t kAluSrc1NegateBit = 0x04000000u;

constexpr Edit kL4NormalNegateEdits[] = {
    // Instr 16: dp3 r1.x___, r4.zxyy, c44.zxyy -> -r4.zxyy
    {48, 0xC8010001u, 0xC8010001u}, {49, 0x00BEBE00u, 0x04BEBE00u}, {50, 0xB0042C00u, 0xB0042C00u},
    // Instr 17: dp3 r1._y__, r4.zxyy, c45.zxyy -> -r4.zxyy
    {51, 0xC8020001u, 0xC8020001u}, {52, 0x00BEBE00u, 0x04BEBE00u}, {53, 0xB0042D00u, 0xB0042D00u},
    // Instr 18: dp3 r1.__z_, r4.zxyy, c46.zxyy -> -r4.zxyy
    {54, 0xC8040001u, 0xC8040001u}, {55, 0x00BEBE00u, 0x04BEBE00u}, {56, 0xB0042E00u, 0xB0042E00u},
    // Instr 19: dp3 r1.___w, r4.zxyy, c47.zxyy -> -r4.zxyy
    {57, 0xC8080001u, 0xC8080001u}, {58, 0x00BEBE00u, 0x04BEBE00u}, {59, 0xB0042F00u, 0xB0042F00u},
    // Instr 20: dp3 r2.x___, r4.zxyy, c52.zxyy -> -r4.zxyy
    {60, 0xC8010002u, 0xC8010002u}, {61, 0x00BEBE00u, 0x04BEBE00u}, {62, 0xB0043400u, 0xB0043400u},
    // Instr 21: dp3 r2._y__, r4.zxyy, c53.zxyy (+ subsc) -> -r4.zxyy
    {63, 0xB8120002u, 0xB8120002u}, {64, 0x00BEBEC0u, 0x04BEBEC0u}, {65, 0x90043504u, 0x90043504u},
    // Instr 22: dp3 r2.__z_, r4.zxyy, c54.zxyy (+ maxs) -> -r4.zxyy
    {66, 0x14040002u, 0x14040002u}, {67, 0x00BEBE6Cu, 0x04BEBE6Cu}, {68, 0xB0043600u, 0xB0043600u},
    // Instr 23: dp3 r2.___w, r4.zxyy, c55.zxyy (+ muls_prev_sat) -> -r4.zxyy
    {69, 0x0E180002u, 0x0E180002u}, {70, 0x00BEBEC6u, 0x04BEBEC6u}, {71, 0xB0043703u, 0xB0043703u},
};
constexpr Plan kL4NormalNegatePlan = {120, kL4NormalNegateEdits, sizeof(kL4NormalNegateEdits) / sizeof(Edit)};

enum class L4NormalMode { kOff = 0, kAll = 1, kOpaquePsOnly = 2 };

inline L4NormalMode ParseTestNormalMode(const char* value) {
  if (!value) return L4NormalMode::kOff;
  if (std::strcmp(value, "negate") == 0) return L4NormalMode::kAll;
  if (std::strcmp(value, "negate_opaque") == 0) return L4NormalMode::kOpaquePsOnly;
  return L4NormalMode::kOff;
}

inline L4NormalMode TestNormalMode() {
  static const L4NormalMode mode = ParseTestNormalMode(std::getenv("R3HD_TEST_LIT_NORMAL_SIGN"));
  return mode;
}

inline const char* TestNormalModeName(L4NormalMode mode) {
  switch (mode) {
    case L4NormalMode::kAll:
      return "negate";
    case L4NormalMode::kOpaquePsOnly:
      return "negate_opaque";
    default:
      return "original";
  }
}

inline bool TestNormalMatches(L4NormalMode mode, uint64_t pixel_shader_hash) {
  if (mode == L4NormalMode::kAll) return true;
  if (mode == L4NormalMode::kOpaquePsOnly) return pixel_shader_hash == kOpaquePropPixelShaderHash;
  return false;
}

// Composed fail-closed microcode transform for all four (apply_uv_scroll x apply_normal_negate) configurations.
// Returns empty when neither edit is requested or if any checked dword does not match the expected title microcode.
inline std::vector<uint32_t> CorrectedComposed(const std::vector<uint32_t>& ucode, bool apply_uv_scroll,
                                               bool apply_normal_negate) {
  if (!apply_uv_scroll && !apply_normal_negate) return {};
  if (ucode.size() != kVertexPlan.dword_count) return {};
  auto check_plan = [&](const Plan& plan) -> bool {
    for (size_t i = 0; i < plan.edit_count; ++i)
      if (plan.edits[i].dword >= ucode.size() || ucode[plan.edits[i].dword] != plan.edits[i].expect) return false;
    return true;
  };
  if (apply_uv_scroll && !check_plan(kVertexPlan)) return {};
  if (apply_normal_negate && !check_plan(kL4NormalNegatePlan)) return {};
  std::vector<uint32_t> out(ucode);
  if (apply_uv_scroll)
    for (size_t i = 0; i < kVertexPlan.edit_count; ++i) out[kVertexPlan.edits[i].dword] = kVertexPlan.edits[i].value;
  if (apply_normal_negate)
    for (size_t i = 0; i < kL4NormalNegatePlan.edit_count; ++i)
      out[kL4NormalNegatePlan.edits[i].dword] = kL4NormalNegatePlan.edits[i].value;
  for (uint32_t& v : out) v = ByteSwap(v);
  return out;
}
}  // namespace uvslit
