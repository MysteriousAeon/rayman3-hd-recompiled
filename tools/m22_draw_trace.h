// M22: read-only draw-state trace of ONE guest frame, for fidelity investigation (which draw produces a pixel,
// with which guest state). Installed as include/rex/m22_draw_trace.h by tools/m22_runtime_patch.py and called
// from the D3D12 command processor only. Off unless R3HD_M22_DRAW_TRACE=1 is set; then the frame that follows an
// explicit frame capture (the M6 request file, so at most as many traces as readbacks) is written to
// m22_draws_<swap>.bin in the process working directory (a private run directory: the file holds guest
// register values, shader microcode, vertex and index bytes and the first bytes of bound textures, all
// game-derived). It never changes what the backend renders and writes no guest memory.
//
// File: records, host byte order. Every record starts with { magic 'M22D', kind, payload bytes }.
//   kind 0 draw:   Head, vertex bindings (BindingHead + AttributeRow[] each), texture rows (TextureRow each),
//                  registers 0x2000..0x23FF, 0x4000..0x48BF, index bytes, vertex bytes per binding
//   kind 1 copy:   registers 0x2000..0x23FF (a resolve or clear, RB_COPY_CONTROL at 0x2318)
//   kind 2 shader: hash, type, dword count, microcode dwords (once per distinct shader in the file)
#pragma once
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <unordered_set>
#include <vector>

namespace m22draw {
constexpr uint32_t kMagic = 0x4D323244;
constexpr uint32_t kVertexCap = 1u << 20, kIndexCap = 1u << 20, kTextureHead = 64;
constexpr uint64_t kFileCap = 384ull << 20;

// Bytes that may be read at a guest physical address: capped, and never past the 512 MB physical view.
inline uint32_t Bounded(uint32_t address, uint32_t bytes, uint32_t cap) {
  const uint32_t room = 0x20000000u - (address & 0x1FFFFFFFu);
  return std::min(std::min(bytes, cap), room);
}

struct Head {
  uint32_t draw, primitive, index_count, indexed, index_format, index_endian, index_base, index_bytes;
  uint64_t vs_hash, ps_hash;
  uint32_t binding_count, texture_count;
};
struct BindingHead { uint32_t fetch_constant, stride_words, attribute_count, address, size_bytes, captured_bytes; };
struct AttributeRow { uint32_t format, offset_words, is_signed, is_integer, exp_adjust, result_register; };
struct TextureRow { uint32_t fetch_constant, base, head_bytes; uint8_t head[kTextureHead]; };

struct State {
  bool enabled = std::getenv("R3HD_M22_DRAW_TRACE") != nullptr;
  uint64_t armed_swap = 0;  // trace the draws issued while the swap counter equals this value
  std::FILE* file = nullptr;
  uint64_t written = 0;
  uint32_t draw = 0;
  std::unordered_set<uint64_t> shaders;
};
inline State& state() { static State s; return s; }

// Called once per swap on the command-processor thread, after the swap was counted. `captured` = this swap
// was an explicit frame capture.
inline void OnSwap(uint64_t swap, bool captured) {
  State& s = state();
  if (!s.enabled) return;
  if (s.file) { std::fclose(s.file); s.file = nullptr; s.armed_swap = 0; }
  if (!captured) return;
  char name[48];
  std::snprintf(name, sizeof(name), "m22_draws_%05llu.bin", static_cast<unsigned long long>(swap));
  s.file = std::fopen(name, "wb");
  s.armed_swap = swap; s.written = 0; s.draw = 0; s.shaders.clear();
}

inline bool Tracing(uint64_t swap) {
  State& s = state();
  return s.file && s.armed_swap == swap && s.written < kFileCap;
}

inline void Put(const void* data, size_t bytes) {
  State& s = state();
  std::fwrite(data, 1, bytes, s.file);
  s.written += bytes;
}

inline void Record(uint32_t kind, const std::vector<uint8_t>& payload) {
  uint32_t head[3] = {kMagic, kind, uint32_t(payload.size())};
  Put(head, sizeof(head));
  Put(payload.data(), payload.size());
}

template <typename T>
inline void Append(std::vector<uint8_t>& out, const T& value) {
  const auto* p = reinterpret_cast<const uint8_t*>(&value);
  out.insert(out.end(), p, p + sizeof(T));
}
inline void Append(std::vector<uint8_t>& out, const void* data, size_t bytes) {
  const auto* p = static_cast<const uint8_t*>(data);
  out.insert(out.end(), p, p + bytes);
}

inline void Shader(uint64_t hash, uint32_t type, const uint32_t* dwords, uint32_t count) {
  if (!state().shaders.insert(hash ^ (uint64_t(type) << 63)).second) return;
  std::vector<uint8_t> payload;
  Append(payload, hash); Append(payload, type); Append(payload, count);
  Append(payload, dwords, size_t(count) * 4);
  Record(2, payload);
}

inline void Copy(const uint32_t* regs) {
  std::vector<uint8_t> payload;
  Append(payload, &regs[0x2000], 0x400 * 4);
  Record(1, payload);
}
}  // namespace m22draw
