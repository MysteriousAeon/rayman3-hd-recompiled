// M23 (D-052, D-054): optional separate coordinates for the second layer of the title's two-layer translucent
// blend shader `tvt_tVT`. Installed as include/rex/m23_water_layers.h by tools/m23_runtime_patch.py and used by
// the D3D12 command processor only. The file and namespace keep the option's first name ("water layers", from
// the texture names); on screen the two materials seen so far are a haze sheet (The Bog of Murk) and a cloud
// layer (the Land of the Livid Dead), so the option is called "layer coordinates" (R3HD_LAYER_COORDS).
//
// What the title does (RE_NOTES "M23"): its pixel shader `tvt_tVT` samples both texture layers with the first
// layer's coordinates, although the original shader kept in the same source file gives each layer its own
// (`add oT1,v4,c11`), the vertex buffer still carries the second set and the title still animates the second
// layer's scroll offset in vertex constant c11 every frame. The two layers therefore move together instead of
// against each other. That is the Xbox 360 HD release's own behaviour (class B), so it stays the default.
//
// With R3HD_LAYER_COORDS=separate the host draws that one shader pair from edited copies of the title's
// microcode: the vertex shader's dead instruction becomes `add o3.xy, r3.xy, c11.xy` (the second coordinate set,
// already fetched into r3, plus its scroll offset) and the pixel shader's second fetch reads r3 instead of r0.
// The vertex edit is the instruction the title's own compiled `2T_D_SPPT.vsh` has at that place in
// `vertexShaderCache_xenon.bin` (`add o1.xy, r3.xy, c11.xy`); the bound copy the title draws with has lost it
// because `tvt_tVT` declares no second coordinate input. Only the export number differs
// (tools/m23_layer_audit.py).
// Nothing else changes: no guest memory, no register, no other shader, no texture. An edit is applied only to
// microcode of the expected length whose dwords at the edited places have the expected values; otherwise the
// pair is drawn as issued.
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <vector>

namespace m23water {
constexpr uint64_t kVertexShaderHash = 0x08E9BEDB27BDDEEEull;  // `2t_d_sppt` bound to a pixel shader without uv2
constexpr uint64_t kPixelShaderHash = 0x27336DBAE47E8650ull;   // `tvt_tVT`

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

// Instruction 15, `max r0._, c0, c0` (a write to nothing) -> `add o3.xy__, r3.xyyy, c11.xyyy`.
constexpr Edit kVertexEdits[] = {
    {45, 0xC8000000u, 0xC8038003u}, {46, 0x00000000u, 0x00B0B000u}, {47, 0x02000000u, 0xA0030B00u}};
// Instruction 3, `tfetch2D r6, r0.xy, tf1` -> `tfetch2D r6, r3.xy, tf1` (source register field, bits 5..10).
constexpr Edit kPixelEdits[] = {{9, 0x10186001u, 0x10186061u}};
constexpr Plan kVertexPlan = {63, kVertexEdits, sizeof(kVertexEdits) / sizeof(Edit)};
constexpr Plan kPixelPlan = {42, kPixelEdits, sizeof(kPixelEdits) / sizeof(Edit)};

// "separate" selects the correction; anything else, or no variable, is the title's own behaviour.
inline bool Selected(const char* value) { return value && std::strcmp(value, "separate") == 0; }
// R3HD_LAYER_COORDS decides when it is set (to anything); the option's first name R3HD_WATER_LAYERS is read
// only without it, so earlier scripts keep working and a stale old variable cannot override the new one.
inline const char* Value(const char* current, const char* legacy) { return current ? current : legacy; }
inline bool Enabled() {
  static const bool on = Selected(Value(std::getenv("R3HD_LAYER_COORDS"), std::getenv("R3HD_WATER_LAYERS")));
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
}  // namespace m23water
