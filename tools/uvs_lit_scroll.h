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
}  // namespace uvslit
