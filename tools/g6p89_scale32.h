// G6-P89 / G6-P92 / G6-P140: native 3:2 (1.5x, 1920x1080) draw resolution scale, D3D12 host render targets only.
// Installed as include/rex/g6p89_scale32.h by tools/g6p89_scale32_patch.py.
//
// Gate (off by default; no user-facing Settings exposure yet):
//   * Primary development opt-in: R3HD_RENDER_SCALE_3_2 is exactly "1" (works in both attended play via play.ps1 and
//     hidden runs). Any other non-empty value (e.g. "0") explicitly disables 3:2.
//   * Legacy hidden-test alias (when R3HD_RENDER_SCALE_3_2 is unset/empty): R3HD_NONINTRUSIVE is set AND
//     R3HD_TEST_G6P89_SCALE_3_2 is exactly "1".
// The D3D12 command processor calls Activate() once, before the render target and texture caches exist, after checking
// the device (tiled resources for the scaled resolve memory). If the device cannot initialize 3:2, LogInactive() logs
// the reason and the configured integer scale stays in effect (clean initialization fallback). Without activation every
// helper here is the integer path: Scale{x, y, 1}, whose arithmetic is the SDK's original `value * scale` expression,
// so scales 1 / 2 / 3 keep their exact meaning and the integer packed fields (3-bit shader fields) are never given 1.5.
//
// While active (Scale{3, 3, 2}):
//   * host extent = guest extent * 3 / 2, exact; a non-integer result is refused, never rounded;
//   * scaled resolve memory = 9/4 of guest bytes, in 64-byte guest groups (2 x 2 SDK Nx1 units at 4 bytes per block ->
//     3 x 3 host Nx1 sub-units, column-major, at group guest address x 9/4: model R of G6-P88, tools/g6p88_sdk_scaled_model.py);
//   * any operation outside the supported set calls Refuse(): one bounded `G6P89 REFUSE` line, the log is flushed and the
//     process ends with exit code 137. There is no silent fallback to another scale. The integer accessors of the caches
//     refuse too, so a scale-dependent site that was not converted cannot run with a wrong scale.
// Output lines (bounded): G6P89 active / rt_create / resolve_map / swap_source / stats / REFUSE.
#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <thread>
#include <rex/logging.h>

namespace g6p89 {

constexpr uint32_t kNum = 3;
constexpr uint32_t kDen = 2;
constexpr uint32_t kGroupGuestBytes = 64;   // 2 x 2 SDK units of 16 bytes (4 bytes per block)
constexpr uint32_t kGroupHostBytes = 144;   // 3 x 3 host sub-units of 16 bytes
constexpr int kExitCode = 137;
constexpr uint64_t kStatsSwaps = 600;
constexpr unsigned kRtLines = 64;
constexpr unsigned kResolveMapLines = 16;
constexpr unsigned kSwapLines = 8;

enum Reason : uint32_t {
  kIntegerAccessor,   // an integer-scale accessor was reached while 3:2 is active (unconverted site)
  kNotInteger,        // guest extent * 3 / 2 is not an integer
  kOverflow,          // checked host size arithmetic overflowed
  kAddressAlign,      // a scaled base address is not a 64-byte group boundary
  kResolveShader,     // resolve copy shader other than fast 32bpp 1x/2x MSAA
  kResolveSize,       // resolve extent with a partial copy thread or group (ResolveExtentExact)
  kResolveDest,       // array / 3D resolve destination
  kResolveClearOnly,  // reserved (never raised)
  kTextureFormat,     // a scaled-resolved range sampled with a load shader that has no 3:2 variant
  kTextureLayout,     // mips, packed mip tail, array / 3D, block-compressed or odd-sized scaled texture
  kViewport,          // odd guest viewport edge
  kScissor,           // odd guest scissor edge
  kMemExport,         // pixel- or vertex-shader memory export while 3:2 is active
  kHostDepthStore,    // host depth store path (not supported at 3:2)
  kReadback,          // reserved: readback / downscale (cvar readback_resolve, default none) reaches the
                      // refusing integer accessors instead
  kPath,              // reserved: 3:2 forces the host render target path; other backends never activate
  kTransfer,          // reserved: transfer rectangles are whole tiles, always integer at 3:2
  kReasonCount
};

inline const char* ReasonName(uint32_t r) {
  static const char* const names[kReasonCount] = {
      "integer_accessor", "not_integer", "overflow",     "address_align", "resolve_shader", "resolve_size",
      "resolve_dest",     "reserved",    "texture_format", "texture_layout", "viewport",     "scissor",
      "memexport",        "host_depth_store", "readback", "path",          "transfer"};
  return r < kReasonCount ? names[r] : "?";
}

inline bool ParseEnable(const char* dev_flag, const char* nonintrusive, const char* legacy_flag) {
  if (dev_flag != nullptr && dev_flag[0] != '\0') {
    return std::strcmp(dev_flag, "1") == 0;
  }
  return nonintrusive != nullptr && legacy_flag != nullptr && std::strcmp(legacy_flag, "1") == 0;
}

// Development opt-in or legacy hidden-test request (read once).
inline bool Requested() {
  static const bool requested = ParseEnable(std::getenv("R3HD_RENDER_SCALE_3_2"),
                                            std::getenv("R3HD_NONINTRUSIVE"),
                                            std::getenv("R3HD_TEST_G6P89_SCALE_3_2"));
  return requested;
}

inline std::atomic<bool>& ActiveFlag() {
  static std::atomic<bool> active{false};
  return active;
}

inline bool Active() { return ActiveFlag().load(std::memory_order_relaxed); }

struct Stats {
  std::mutex lock;
  uint64_t resolves = 0, scaled_loads = 0, transfers = 0, draws = 0, swaps = 0;
  // G6-P92: resolves whose host height is not a multiple of 8 rows (admitted by the 4-row copy groups).
  uint64_t edge_resolves = 0;
  unsigned rt_lines = 0, resolve_map_lines = 0, swap_lines = 0;
  uint32_t resolve_seen[kResolveMapLines][3] = {};  // G6-P92: distinct (base, width, height) of resolve_map lines
  uint32_t swap_seen[kSwapLines][2] = {};
};

inline Stats& GetStats() {
  static Stats stats;
  return stats;
}

[[noreturn]] inline void Refuse(uint32_t reason, uint64_t a = 0, uint64_t b = 0) {
  // 0 = no refusal yet, 1 = the first refusing thread is writing its line, 2 = written and flushed.
  static std::atomic<int> state{0};
  int expected = 0;
  if (state.compare_exchange_strong(expected, 1)) {
    Stats& s = GetStats();
    REXGPU_ERROR("G6P89 REFUSE reason={} a={} b={} swap={} resolves={} scaled_loads={} transfers={} draws={} "
                 "action=exit code={}",
                 ReasonName(reason), a, b, s.swaps, s.resolves, s.scaled_loads, s.transfers, s.draws, kExitCode);
    rex::FlushLogging();
    state.store(2);
  } else {
    // Another thread is writing the refusal line: let it finish (bounded, 2 s) so the line is not lost.
    for (int i = 0; i < 2000 && state.load() != 2; ++i) {
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  }
  std::_Exit(kExitCode);
}

// Earlier chain patches log the integer scale (M15 `rt_create ... scale=`). Inside an IntegerLogScope the integer
// accessors return the 3:2 numerator for that log text instead of refusing; nothing in such a scope computes with it.
inline int& IntegerLogScopeDepth() {
  thread_local int depth = 0;
  return depth;
}
struct IntegerLogScope {
  IntegerLogScope() { ++IntegerLogScopeDepth(); }
  ~IntegerLogScope() { --IntegerLogScopeDepth(); }
  IntegerLogScope(const IntegerLogScope&) = delete;
  IntegerLogScope& operator=(const IntegerLogScope&) = delete;
};
inline bool InIntegerLogScope() { return IntegerLogScopeDepth() > 0; }

// Called once by the D3D12 command processor when Requested() and the device can host the path.
inline void Activate() {
  ActiveFlag().store(true, std::memory_order_relaxed);
  REXGPU_INFO("G6P89 active=1 scale={}/{} path=host_render_targets backend=d3d12 group_bytes={}->{} exit_code={}", kNum,
              kDen, kGroupGuestBytes, kGroupHostBytes, kExitCode);
}

inline void LogInactive(const char* reason) {
  REXGPU_WARN("G6P89 active=0 requested=1 reason={} (normal integer rendering kept)", reason);
}

// Exact per-axis rational draw resolution scale. den == 1: the SDK's integer scale, same expressions as before.
struct Scale {
  uint32_t x = 1;
  uint32_t y = 1;
  uint32_t den = 1;

  bool Scaled() const { return x > den || y > den; }
  bool Rational() const { return den != 1; }
  bool ScaledX() const { return x > den; }
  bool ScaledY() const { return y > den; }

  static uint32_t Axis(uint32_t v, uint32_t num, uint32_t d) {
    if (d == 1) {
      return v * num;  // integer path: the original uint32 expression
    }
    uint64_t p = uint64_t(v) * num;
    if (p % d) Refuse(kNotInteger, v, num);
    p /= d;
    if (p > UINT32_MAX) Refuse(kOverflow, v, num);
    return uint32_t(p);
  }
  uint32_t X(uint32_t guest) const { return Axis(guest, x, den); }
  uint32_t Y(uint32_t guest) const { return Axis(guest, y, den); }
  // Host to guest (exact; used only for whole-guest-pixel host values).
  static uint32_t AxisInv(uint32_t v, uint32_t num, uint32_t d) {
    if (d == 1) return v / num;
    uint64_t p = uint64_t(v) * d;
    if (p % num) Refuse(kNotInteger, v, d);
    return uint32_t(p / num);
  }
  uint32_t InvX(uint32_t host) const { return AxisInv(host, x, den); }
  uint32_t InvY(uint32_t host) const { return AxisInv(host, y, den); }
  float Xf() const { return float(x) / float(den); }
  float Yf() const { return float(y) / float(den); }
  float InvXf() const { return float(den) / float(x); }
  float InvYf() const { return float(den) / float(y); }
  float MaxF() const { return float(x > y ? x : y) / float(den); }
  // Integer-path area (x * y) for the SDK's own code; refused while rational.
  uint32_t IntegerArea() const {
    if (den != 1) Refuse(kIntegerAccessor, x, y);
    return x * y;
  }
  // Exact host bytes for guest bytes (whole scaling groups when rational).
  uint64_t AreaBytes(uint64_t guest) const {
    if (den == 1) return guest * (uint64_t(x) * y);
    uint64_t p = guest * (uint64_t(x) * y);
    uint64_t q = uint64_t(den) * den;
    if (p % q) Refuse(kNotInteger, guest, q);
    return p / q;
  }
  uint32_t TileWidthSamples() const { return X(80); }   // xenos::kEdramTileWidthSamples
  uint32_t TileHeightSamples() const { return Y(16); }  // xenos::kEdramTileHeightSamples
  // Host scaled-resolve offset of a guest address that starts a scaling group (exact).
  uint64_t AddressExact(uint32_t guest) const {
    if (den == 1) return uint64_t(guest) * (uint64_t(x) * y);
    if (guest % kGroupGuestBytes) Refuse(kAddressAlign, guest, kGroupGuestBytes);
    return uint64_t(guest / kGroupGuestBytes) * kGroupHostBytes;
  }
  // Rational only: host [first, end) holding every host byte of guest [start, start + length).
  static void RationalRange(uint32_t start, uint32_t length, uint64_t& first, uint64_t& end) {
    uint64_t g0 = uint64_t(start) / kGroupGuestBytes;
    uint64_t g1 = (uint64_t(start) + length + (kGroupGuestBytes - 1)) / kGroupGuestBytes;
    first = g0 * kGroupHostBytes;
    end = g1 * kGroupHostBytes;
  }
};

// G6-P92: resolve extents of the 3:2 fast 32bpp 1x/2x MSAA copy variant. Each thread copies 8 host pixels along X
// (with an X bound at the scaled width / 8, rounded down), and a thread group is 64 x 4 host pixels (the variant's
// LOCAL_SIZE_Y_XE is 4; GetCopyShader dispatches ceil(host height / 4) groups) with no Y bound. An extent is exact
// when the host width (guest x 3/2) is a whole number of 8-pixel threads and the host height a whole number of
// 4-row groups: then no thread drops pixels and no group writes rows past the rectangle. Guest resolve extents are
// multiples of 8 pixels (xenos::kResolveAlignmentPixels), i.e. 12 host pixels: the height always passes, the width
// needs an even width_div_8 (a multiple of 16 guest pixels).
constexpr uint32_t kResolveThreadWidthPixels = 8;
constexpr uint32_t kResolveGroupHeightLog2 = 2;
inline bool ResolveExtentExact(uint32_t width_div_8, uint32_t height_div_8) {
  uint64_t host_width = uint64_t(width_div_8) * 8u * kNum / kDen;    // 8 guest px x 3/2 = 12 host px, exact
  uint64_t host_height = uint64_t(height_div_8) * 8u * kNum / kDen;
  return host_width % kResolveThreadWidthPixels == 0 && host_height % (1u << kResolveGroupHeightLog2) == 0;
}

inline Scale ActiveScale(uint32_t integer_x, uint32_t integer_y) {
  return Active() ? Scale{kNum, kNum, kDen} : Scale{integer_x, integer_y, 1};
}

// --- Model R (reference for tests; the shader variants implement the same function) ------------------------------
// XeTextureTiledOffset2D of SDK-matching Xenia 0b2ffa314 (texture_address.xesli), 2D only.
inline uint32_t TiledOffset2D(uint32_t x, uint32_t y, uint32_t pitch, uint32_t bpb_log2) {
  pitch = (pitch + 31u) & ~31u;
  uint32_t macro = ((x >> 5) + (y >> 5) * (pitch >> 5)) << (bpb_log2 + 7);
  uint32_t micro = ((x & 7) + ((y & 0xE) << 2)) << bpb_log2;
  uint32_t offset = macro + ((micro & ~0xFu) << 1) + (micro & 0xF) + ((y & 1) << 4);
  return ((offset & ~0x1FFu) << 3) + ((y & 16) << 7) + ((offset & 0x1C0) << 2) +
         (((((y & 8) >> 2) + (x >> 3)) & 3) << 6) + (offset & 0x3F);
}

// Host byte offset of host block (hx, hy) relative to the surface base, 3:2, 4 / 8 / 16 bytes per block.
inline uint32_t RationalScaledOffset2D(uint32_t hx, uint32_t hy, uint32_t pitch, uint32_t bpb_log2) {
  uint32_t unit_width_log2 = (4u - bpb_log2) < 3u ? (4u - bpb_log2) : 3u;
  uint32_t x_subunits = hx >> unit_width_log2;
  uint32_t group_x = x_subunits / 3u, group_y = hy / 3u;
  uint32_t group_guest =
      TiledOffset2D((group_x * 2u) << unit_width_log2, group_y * 2u, pitch, bpb_log2);
  uint32_t sub_x = x_subunits - group_x * 3u, sub_y = hy - group_y * 3u;
  return (group_guest >> 2) * 9u +
         ((((sub_x * 3u + sub_y) << unit_width_log2) + (hx & ((1u << unit_width_log2) - 1u))) << bpb_log2);
}

// --- Bounded diagnostics -------------------------------------------------------------------------------------------
inline void NoteRenderTarget(uint32_t base_tiles, uint32_t pitch_tiles, uint32_t msaa, uint32_t is_depth,
                             uint32_t format, uint32_t guest_w, uint32_t guest_h, uint32_t host_w, uint32_t host_h) {
  if (!Active()) return;
  Stats& s = GetStats();
  std::lock_guard<std::mutex> guard(s.lock);
  if (s.rt_lines >= kRtLines) return;
  ++s.rt_lines;
  REXGPU_INFO("G6P89 rt_create base_tiles={} pitch_tiles={} msaa={} depth={} format={} guest={}x{} host={}x{}",
              base_tiles, pitch_tiles, msaa, is_depth, format, guest_w, guest_h, host_w, host_h);
}

inline void NoteResolve(uint32_t base, uint32_t extent_start, uint32_t extent_length, uint32_t width, uint32_t height,
                        uint32_t host_width, uint32_t host_height, uint64_t host_first, uint64_t host_end) {
  if (!Active()) return;
  Stats& s = GetStats();
  std::lock_guard<std::mutex> guard(s.lock);
  ++s.resolves;
  if (host_height % 8u) ++s.edge_resolves;
  // G6-P92: one line per distinct (base, guest width, guest height), at most kResolveMapLines, so a resolve family
  // that first appears late in a run is still recorded.
  for (unsigned i = 0; i < s.resolve_map_lines; ++i) {
    if (s.resolve_seen[i][0] == base && s.resolve_seen[i][1] == width && s.resolve_seen[i][2] == height) return;
  }
  if (s.resolve_map_lines >= kResolveMapLines) return;
  s.resolve_seen[s.resolve_map_lines][0] = base;
  s.resolve_seen[s.resolve_map_lines][1] = width;
  s.resolve_seen[s.resolve_map_lines][2] = height;
  ++s.resolve_map_lines;
  REXGPU_INFO("G6P89 resolve_map base={:08X} extent={:08X}+{} guest={}x{} host={}x{} scaled_bytes=[{},{}) "
              "ratio_num={} ratio_den={}",
              base, extent_start, extent_length, width, height, host_width, host_height, host_first, host_end,
              host_end - host_first, extent_length);
}

inline void NoteScaledLoad() {
  if (!Active()) return;
  Stats& s = GetStats();
  std::lock_guard<std::mutex> guard(s.lock);
  ++s.scaled_loads;
}

inline void NoteTransfers(uint64_t n) {
  if (!Active() || !n) return;
  Stats& s = GetStats();
  std::lock_guard<std::mutex> guard(s.lock);
  s.transfers += n;
}

inline void NoteDraw() {
  if (!Active()) return;
  Stats& s = GetStats();
  std::lock_guard<std::mutex> guard(s.lock);
  ++s.draws;
}

inline void NoteSwap(uint32_t source_w, uint32_t source_h) {
  if (!Active()) return;
  Stats& s = GetStats();
  std::lock_guard<std::mutex> guard(s.lock);
  ++s.swaps;
  bool seen = false;
  for (unsigned i = 0; i < s.swap_lines; ++i) {
    seen |= s.swap_seen[i][0] == source_w && s.swap_seen[i][1] == source_h;
  }
  if (!seen && s.swap_lines < kSwapLines) {
    s.swap_seen[s.swap_lines][0] = source_w;
    s.swap_seen[s.swap_lines][1] = source_h;
    ++s.swap_lines;
    REXGPU_INFO("G6P89 swap_source swap={} host={}x{}", s.swaps, source_w, source_h);
  }
  if (s.swaps % kStatsSwaps == 0) {
    REXGPU_INFO("G6P89 stats swap={} resolves={} scaled_loads={} transfers={} draws={} edge_resolves={} refusals=0",
                s.swaps, s.resolves, s.scaled_loads, s.transfers, s.draws, s.edge_resolves);
  }
}

}  // namespace g6p89
