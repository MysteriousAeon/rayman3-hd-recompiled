// HD+ lighting L1 (D-150, experimental HD+ candidate): optional bypass of the Xbox 360 HD release's final
// red-correction pass. Installed as include/rex/hdl_red_correction.h by tools/hdl_runtime_patch.py and used by
// the D3D12 command processor only.
//
// What the title does (RE_NOTES "HD lighting: red correction"; E-345): in Hoodlum Headquarters (`fact_*`), the
// Tower of the Leptys (`tower_10`) and Reflux's arena (`knaar_60`) the last draw of each frame is pixel shader
// `DB19DF80422CD907` (`psm/redcorrection.psh`, an HD addition). It copies the scene texture and, wherever the red
// share r / (r + g + b) reaches c0.x, raises green and blue so that the share falls back to c0.x / (c0.x + c0.y).
// Deep red lava becomes salmon pink. That is the HD release's own behaviour (class B), so it stays the default.
//
// With R3HD_RED_CORRECTION=bypass the host uploads that one draw's pixel constant c0.x as 2.0 instead of the
// title's value. The red share of a colour never exceeds 1, so the shader's own test (`sge` against c0.x) fails
// for every pixel, its predicated correction does not run, and it writes the sampled colour with alpha 1: the
// shader's own uncorrected path. The draw is still issued with the same shaders, render target, texture,
// blend and resolve. Nothing else changes: no guest memory or register, no microcode, no other draw, no other
// constant. The shader reads c0 and its literal constants in c255; the host packs used constants in ascending
// order, so c0 is the first four floats of the upload. A shader with the expected hash that does not read c0
// is drawn as issued and logged as refused.
//
// R3HD_RED_CORRECTION_AB=split (hidden runs only: requires R3HD_FRAME_REQUEST and R3HD_NONINTRUSIVE): every red-correction draw is
// issued as the title issues it and then once more with the bypassed c0, the host viewport moved right by half
// the scissor width and the scissor narrowed to the right half. One presented frame then shows the left half of
// the picture twice: through the title's pass on the left, through the bypass on the right (same pixels, same
// game state). Afterwards the viewport, scissor and pixel constant binding are restored for the next draw.
#pragma once
#include <cstdint>
#include <cstdlib>
#include <cstring>

namespace hdlred {
constexpr uint64_t kPixelShaderHash = 0xDB19DF80422CD907ull;  // `psm/redcorrection.psh`
constexpr float kBypassThreshold = 2.0f;                       // above any red share

inline bool Selected() {
  static const bool selected = [] {
    const char* v = std::getenv("R3HD_RED_CORRECTION");
    return v && !std::strcmp(v, "bypass");
  }();
  return selected;
}

inline bool Split() {
  static const bool split = [] {
    const char* v = std::getenv("R3HD_RED_CORRECTION_AB");
    const char* request = std::getenv("R3HD_FRAME_REQUEST");
    return v && !std::strcmp(v, "split") && request && *request && std::getenv("R3HD_NONINTRUSIVE");
  }();
  return split;
}

// Whether the red-correction draw itself gets the bypass (in the split diagnostic the bypassed copy is a second
// draw and the first one stays as issued).
inline bool Wanted() { return Selected() && !Split(); }

// The constant layout the bypass expects: float constant c0 is read, so it is the first packed constant.
inline bool LayoutMatches(const uint64_t bitmap[4], uint32_t float_count) {
  return float_count >= 1 && (bitmap[0] & 1) != 0;
}
}  // namespace hdlred
