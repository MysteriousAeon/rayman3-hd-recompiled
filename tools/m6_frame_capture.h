// Bounded, request-driven frame readback for hidden M6 runs.
// CaptureAt is called on the present/command-processing thread and caches one
// decision per swap because M3 asks once for logging and again for readback.
#pragma once
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <string>
#include <rex/logging.h>
#include <rex/ui/presenter.h>

namespace m6frame {
constexpr uint64_t kReadbackLimit = 8;
constexpr auto kPollInterval = std::chrono::milliseconds(250);

struct SeenFrame {
  uint64_t hash = 0;
  uint32_t width = 0;
  uint32_t height = 0;
};

struct CaptureState {
  uint64_t last_swap = 0;
  uint64_t request_id = 0;
  uint64_t last_consumed_id = 0;
  uint64_t attempts = 0;
  uint64_t saved_count = 0;
  bool has_swap = false;
  bool decision = false;
  bool has_polled = false;
  std::chrono::steady_clock::time_point last_poll{};
  std::array<SeenFrame, kReadbackLimit> seen{};
  size_t seen_count = 0;
};

inline CaptureState& State() {
  static CaptureState state;
  return state;
}

inline uint64_t RequestIdForSwap(uint64_t swap) {
  const auto& state = State();
  return state.has_swap && state.last_swap == swap && state.decision ? state.request_id : 0;
}

inline uint64_t ReadbackAttempts() { return State().attempts; }

inline bool CaptureAt(uint64_t swap) {
  auto& state = State();
  if (state.has_swap && state.last_swap == swap) return state.decision;
  state.has_swap = true;
  state.last_swap = swap;
  state.request_id = 0;
  state.decision = false;
  if (state.attempts >= kReadbackLimit) return false;

  const auto now = std::chrono::steady_clock::now();
  if (!state.has_polled || now - state.last_poll >= kPollInterval) {
    state.has_polled = true;
    state.last_poll = now;
    const char* request_path = std::getenv("R3HD_FRAME_REQUEST");
    if (request_path && *request_path) {
      std::ifstream request_file(request_path);
      std::string token;
      uint64_t requested_id = 0;
      bool valid = bool(request_file >> token) && !token.empty();
      if (valid) {
        for (char digit : token) {
          if (digit < '0' || digit > '9') { valid = false; break; }
          uint64_t value = uint64_t(digit - '0');
          if (requested_id > (std::numeric_limits<uint64_t>::max() - value) / 10) { valid = false; break; }
          requested_id = requested_id * 10 + value;
        }
      }
      if (valid && requested_id > 0 && requested_id > state.last_consumed_id) {
        state.request_id = requested_id;
        state.last_consumed_id = requested_id;
        state.decision = true;
        ++state.attempts;
      }
    }
  }
  return state.decision;
}

inline uint64_t PixelHash(const rex::ui::RawImage& image, bool* valid) {
  *valid = false;
  const uint64_t row_bytes = uint64_t(image.width) * 4;
  if (!image.width || !image.height || image.stride < row_bytes ||
      row_bytes > std::numeric_limits<size_t>::max()) return 0;
  const size_t stride = image.stride;
  const size_t row_size = static_cast<size_t>(row_bytes);
  if (image.height > 1 && stride > (std::numeric_limits<size_t>::max() - row_size) / (image.height - 1)) return 0;
  const size_t required = size_t(image.height - 1) * stride + row_size;
  if (image.data.size() < required) return 0;

  // FNV-1a over visible RGB pixels, excluding X8 and per-row padding so the
  // identity matches the BMP content rather than an unused channel.
  uint64_t hash = 14695981039346656037ull;
  for (uint32_t y = 0; y < image.height; ++y) {
    const uint8_t* row = image.data.data() + size_t(y) * stride;
    for (uint32_t x = 0; x < image.width; ++x) {
      for (unsigned channel = 0; channel < 3; ++channel) {
        hash ^= row[size_t(x) * 4 + channel];
        hash *= 1099511628211ull;
      }
    }
  }
  *valid = true;
  return hash;
}

template <typename WriteFn>
inline bool SaveIfNew(const rex::ui::RawImage& image, const char* name, uint64_t swap, WriteFn write_bmp) {
  auto& state = State();
  const uint64_t request_id = RequestIdForSwap(swap);
  bool valid = false;
  const uint64_t hash = PixelHash(image, &valid);
  if (!valid) {
    REXGPU_INFO("M6 frame_capture request_id={} swap={} hash=unavailable width={} height={} saved=false saved_count={}/{} attempts={}/{} duplicate=false result=invalid_image",
                request_id, swap, image.width, image.height, state.saved_count, kReadbackLimit, state.attempts, kReadbackLimit);
    return false;
  }
  for (size_t i = 0; i < state.seen_count; ++i) {
    const auto& prior = state.seen[i];
    if (prior.hash == hash && prior.width == image.width && prior.height == image.height) {
      REXGPU_INFO("M6 frame_capture request_id={} swap={} hash={:016X} width={} height={} saved=false saved_count={}/{} attempts={}/{} duplicate=true",
                  request_id, swap, hash, image.width, image.height, state.saved_count, kReadbackLimit, state.attempts, kReadbackLimit);
      return false;
    }
  }

  const bool saved = write_bmp(name, image);
  if (saved && state.seen_count < state.seen.size()) {
    state.seen[state.seen_count++] = {hash, image.width, image.height};
    ++state.saved_count;
  }
  REXGPU_INFO("M6 frame_capture request_id={} swap={} hash={:016X} width={} height={} saved={} saved_count={}/{} attempts={}/{} duplicate=false",
              request_id, swap, hash, image.width, image.height, saved, state.saved_count, kReadbackLimit, state.attempts, kReadbackLimit);
  return saved;
}

inline void ReadbackUnavailable(uint64_t swap) {
  const auto& state = State();
  REXGPU_INFO("M6 frame_capture request_id={} swap={} hash=unavailable width=0 height=0 saved=false saved_count={}/{} attempts={}/{} duplicate=false result=readback_unavailable",
              RequestIdForSwap(swap), swap, state.saved_count, kReadbackLimit, state.attempts, kReadbackLimit);
}
}  // namespace m6frame
