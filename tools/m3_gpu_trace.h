// Milestone 3 observational GPU instrumentation for pinned ReXGlue c94f5eb.
// Installed as include/rex/m3_gpu_trace.h by tools/m3_runtime_patch.py and used only
// from src/graphics/d3d12/command_processor.cpp. It counts and logs; it never changes
// what the backend renders. Dumps go to the process working directory (a private,
// git-ignored run directory): shader microcode and captured frames are game-derived.
#pragma once
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <unordered_map>
#include <vector>
#include <rex/logging.h>
#include <rex/ui/presenter.h>

namespace m3gpu {
struct Counters {
  std::atomic<uint64_t> draws{0}, copies{0}, clears{0}, swaps{0}, shader_packets{0}, refreshed{0};
  uint64_t draws_at_swap = 0, copies_at_swap = 0, clears_at_swap = 0;
};
inline Counters& counters() { static Counters c; return c; }
inline bool Sampled(uint64_t n) { return (n & (n - 1)) == 0; }

inline uint64_t Fnv(const uint8_t* p, size_t n) {
  uint64_t h = 1469598103934665603ull;
  for (size_t i = 0; i < n; ++i) { h ^= p[i]; h *= 1099511628211ull; }
  return h;
}

// One line + one dump per distinct microcode blob; repeat submissions are only counted.
inline void ShaderSubmit(unsigned type, uint32_t guest_address, const uint32_t* host, uint32_t dwords) {
  static std::mutex mutex;
  static std::unordered_map<uint64_t, uint64_t> seen;
  auto& c = counters();
  ++c.shader_packets;
  uint64_t hash = Fnv(reinterpret_cast<const uint8_t*>(host), size_t(dwords) * 4) ^ (uint64_t(type) << 63);
  std::lock_guard<std::mutex> lock(mutex);
  if (seen[hash]++) return;
  char name[64];
  std::snprintf(name, sizeof(name), "m3_shader_%u_%016llX.bin", type, static_cast<unsigned long long>(hash));
  if (FILE* f = std::fopen(name, "wb")) { std::fwrite(host, 4, dwords, f); std::fclose(f); }
  REXGPU_INFO("M3 shader_distinct type={} hash={:016X} dwords={} first_guest_address={:08X} distinct={} packets={}",
              type, hash, dwords, guest_address, seen.size(), c.shader_packets.load());
}

// regs: Xenos register file values (0x2000 RB_SURFACE_INFO, 0x2001 RB_COLOR_INFO, 0x2002 RB_DEPTH_INFO).
inline void Draw(const uint32_t* regs, unsigned primitive, uint32_t index_count) {
  uint64_t n = ++counters().draws;
  if (Sampled(n))
    REXGPU_INFO("M3 draw count={} primitive={} indices={} surface_info={:08X} color_info={:08X} depth_info={:08X} modecontrol={:08X}",
                n, primitive, index_count, regs[0x2000], regs[0x2001], regs[0x2002], regs[0x2208]);
}

// Xenos resolves (and clears, via RB_COPY_CONTROL bits 8/9) arrive as kCopy-mode draws.
inline void Copy(const uint32_t* regs) {
  auto& c = counters();
  uint64_t n = ++c.copies;
  bool clear = (regs[0x2318] & 0x300) != 0;
  uint64_t k = clear ? ++c.clears : c.clears.load();
  if (Sampled(n) || (clear && Sampled(k)))
    REXGPU_INFO("M3 copy count={} clears={} copy_control={:08X} dest_base={:08X} dest_pitch={:08X} dest_info={:08X} surface_info={:08X} color_info={:08X}",
                n, k, regs[0x2318], regs[0x2319], regs[0x231A], regs[0x231B], regs[0x2000], regs[0x2001]);
}

inline bool CaptureAt(uint64_t swap) {
  switch (swap) { case 2: case 30: case 120: case 300: case 600: case 900: case 1500: case 2400: case 3600: case 5400: return true; }
  return false;
}

inline void WriteBmp(const char* name, const rex::ui::RawImage& image) {
  FILE* f = std::fopen(name, "wb");
  if (!f) return;
  uint32_t w = image.width, h = image.height, row = w * 3 + ((4 - (w * 3) % 4) % 4), size = 54 + row * h;
  uint8_t header[54] = {'B', 'M'};
  auto put = [&](int at, uint32_t v) { std::memcpy(header + at, &v, 4); };
  put(2, size); put(10, 54); put(14, 40); put(18, w); put(22, h);
  header[26] = 1; header[28] = 24; put(34, row * h);
  std::fwrite(header, 1, 54, f);
  std::vector<uint8_t> line(row);
  for (uint32_t y = 0; y < h; ++y) {
    const uint8_t* src = image.data.data() + size_t(h - 1 - y) * image.stride;
    for (uint32_t x = 0; x < w; ++x) { line[x * 3] = src[x * 4 + 2]; line[x * 3 + 1] = src[x * 4 + 1]; line[x * 3 + 2] = src[x * 4]; }
    std::fwrite(line.data(), 1, row, f);
  }
  std::fclose(f);
}

// Called at the end of the backend's swap handling, on the command-processor thread.
inline void Swap(rex::ui::Presenter* presenter, uint32_t frontbuffer_ptr, uint32_t packet_width, uint32_t packet_height,
                 uint32_t source_width, uint32_t source_height, unsigned source_dxgi_format, unsigned guest_format,
                 uint32_t output_width, uint32_t output_height, uint32_t display_width, uint32_t display_height) {
  auto& c = counters();
  uint64_t n = ++c.swaps;
  uint64_t draws = c.draws, copies = c.copies, clears = c.clears;
  if (Sampled(n) || n % 300 == 0 || CaptureAt(n))
    REXGPU_INFO("M3 swap count={} frontbuffer={:08X} packet={}x{} source={}x{} dxgi_format={} guest_format={} output={}x{} display={}x{} "
                "draws_since={} copies_since={} clears_since={} draws_total={} copies_total={} shader_packets={} guest_output_refreshed={}",
                n, frontbuffer_ptr, packet_width, packet_height, source_width, source_height, source_dxgi_format, guest_format,
                output_width, output_height, display_width, display_height, draws - c.draws_at_swap, copies - c.copies_at_swap,
                clears - c.clears_at_swap, draws, copies, c.shader_packets.load(), c.refreshed.load());
  c.draws_at_swap = draws; c.copies_at_swap = copies; c.clears_at_swap = clears;
  if (!presenter || !CaptureAt(n)) return;
  rex::ui::RawImage image;
  if (!presenter->CaptureGuestOutput(image) || !image.width || !image.height) {
    REXGPU_INFO("M3 frame_capture swap={} result=unavailable", n);
    return;
  }
  // Coarse content statistics so a black/constant frame is distinguishable in the log.
  uint64_t sum = 0, nonblack = 0, pixels = uint64_t(image.width) * image.height;
  uint32_t first = 0; bool varies = false;
  std::unordered_map<uint32_t, uint32_t> colors;
  for (uint32_t y = 0; y < image.height; ++y) {
    const uint8_t* p = image.data.data() + size_t(y) * image.stride;
    for (uint32_t x = 0; x < image.width; ++x, p += 4) {
      uint32_t rgb = p[0] | (p[1] << 8) | (p[2] << 16);
      if (!x && !y) first = rgb; else if (rgb != first) varies = true;
      sum += p[0] + p[1] + p[2]; nonblack += rgb != 0;
      if ((x & 7) == 0 && (y & 7) == 0 && colors.size() < 65536) ++colors[rgb & 0xF8F8F8];
    }
  }
  char name[48];
  std::snprintf(name, sizeof(name), "m3_frame_%05llu.bmp", static_cast<unsigned long long>(n));
  WriteBmp(name, image);
  REXGPU_INFO("M3 frame_capture swap={} file={} size={}x{} mean_channel={:.2f} nonblack_fraction={:.4f} pixels_vary={} sampled_distinct_colors={}",
              n, name, image.width, image.height, double(sum) / double(pixels * 3), double(nonblack) / double(pixels), varies, colors.size());
}
}  // namespace m3gpu
