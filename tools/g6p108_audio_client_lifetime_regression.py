#!/usr/bin/env python3
"""G6-P108 / G6-P109 (E-591 / E-592, D-346): Deterministic offline reproduction &
verification suite for ReXGlue AudioSystem client lifetime and shutdown safety.

Verifies:
1. Pinned ReXGlue SDK (`c94f5ebdcb3c9d1a460ca48e04f9758448f8d518`) patch-chain integrity:
   - `tools/g6p109_audio_client_lifetime_patch.py` applies cleanly to pinned `c94f5eb`
     `audio_system.h` and `audio_system.cpp`, is idempotent, preserves LF endings, and
     fails closed on source drift (missing anchor, duplicate anchor, partial patch).
   - `tools/build_milestone8.bat` runs `g6p109_audio_client_lifetime_patch.py` once before
     `cmake -S external` and runs this regression once before `echo M8_BUILD_OK`.
   - Guest-visible XAudio handle encoding (`0x41550000 | index`) is preserved.
2. Verbatim source-extracted C++20 + ASan deterministic harness:
   - Extracts verbatim `AudioSystem` methods (`WorkerThreadMain` dispatch block,
     `FindFreeClient`, `Shutdown`, `RegisterClient`, `SubmitFrame`, `UnregisterClient`,
     and patched `FinalizeClientLocked`) and the `clients_` struct directly from:
     (a) unpatched `git show c94f5eb:...` (Release `-DNDEBUG` negative controls),
     (b) patched working tree (Release `-DNDEBUG` positive controls), and
     (c) patched working tree (Debug, assertions enabled, positive controls).
   - Uses real `std::thread`, real `std::recursive_mutex`, and explicit barrier
     synchronization (zero sleeps, zero probabilistic loops) to verify:
     * `safe_ordering`: Unpatched PASS, Patched Release/Debug PASS.
     * `hazard_a_null_deref`: Unpatched NULL SEGV (`0x000000000000`), Patched safe no-op.
     * `hazard_b_wrapped_arg_uaf`: Unpatched ASan UAF, Patched safe read + deferred free.
     * `hazard_c_slot_reuse_aba`: Unpatched misdelivery (rc 42), Patched slot reservation.
     * `self_unregister`: Unpatched ASan UAF/crash, Patched no deadlock + deferred cleanup.
     * `multiple_clients`: Unpatched PASS, Patched PASS.
     * `shutdown_in_flight`: Unpatched ASan UAF/crash, Patched waits & finalizes cleanly.
     * `repeated_register_unregister`: Unpatched PASS, Patched PASS (incl. 8-slot exhaustion & reclamation).
     * `exception_unwind` (Patched): RAII guard still finalizes deferred unregister on unwind.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import g6p109_audio_client_lifetime_patch as patch_mod  # noqa: E402

SDK = ROOT / "external" / "rexglue-sdk"
AUDIO_SYSTEM_CPP = SDK / "src" / "audio" / "audio_system.cpp"
AUDIO_SYSTEM_H = SDK / "include" / "rex" / "audio" / "audio_system.h"
XBOXKRNL_AUDIO_CPP = SDK / "src" / "kernel" / "xboxkrnl" / "xboxkrnl_audio.cpp"
ASSERT_H = SDK / "include" / "rex" / "assert.h"

EXPECTED_SDK_PIN = "c94f5ebdcb3c9d1a460ca48e04f9758448f8d518"
DEFAULT_VCVARS = r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
DEFAULT_LLVM_BIN = r"C:\Program Files\LLVM\bin"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_snippet(source: str, start_anchor: str, end_anchor: str) -> str:
    s_idx = source.find(start_anchor)
    if s_idx < 0:
        raise RuntimeError(f"Start anchor not found: {start_anchor!r}")
    e_idx = source.find(end_anchor, s_idx)
    if e_idx < 0:
        raise RuntimeError(f"End anchor not found: {end_anchor!r}")
    return source[s_idx : e_idx + len(end_anchor)]


def extract_audio_system_methods(
    src_text: str, hdr_text: str, patched: bool
) -> dict[str, str]:
    norm_src = src_text.replace("\r\n", "\n")
    norm_hdr = hdr_text.replace("\r\n", "\n")

    clients_struct = extract_snippet(
        norm_hdr,
        "  struct {\n    AudioDriver* driver;",
        "  } clients_[kMaximumClientCount];",
    )
    worker_dispatch = extract_snippet(
        norm_src,
        "      auto global_lock = global_critical_region_.Acquire();",
        "      pumped = true;",
    )
    find_free = extract_snippet(
        norm_src,
        "int AudioSystem::FindFreeClient() {",
        "  return -1;\n}",
    )
    shutdown_fn = extract_snippet(
        norm_src,
        "void AudioSystem::Shutdown() {",
        "\n}\n\n" + ("void AudioSystem::FinalizeClientLocked" if patched else "X_STATUS AudioSystem::RegisterClient"),
    )
    # Trim trailing function header from shutdown_fn
    shutdown_fn = shutdown_fn[: shutdown_fn.rfind("\n}\n") + 2]

    register_client = extract_snippet(
        norm_src,
        "X_STATUS AudioSystem::RegisterClient(uint32_t callback, uint32_t callback_arg, size_t* out_index) {",
        "  return X_STATUS_SUCCESS;\n}",
    )
    if patched:
        finalize_client = extract_snippet(
            norm_src,
            "void AudioSystem::FinalizeClientLocked(size_t index) {",
            "  assert_true(wait_result == rex::thread::WaitResult::kTimeout);\n}",
        )
        submit_frame = extract_snippet(
            norm_src,
            "void AudioSystem::SubmitFrame(size_t index, uint32_t samples_ptr) {",
            "  client.driver->SubmitFrame(samples_ptr);\n}",
        )
        unregister_client = extract_snippet(
            norm_src,
            "void AudioSystem::UnregisterClient(size_t index) {",
            "  if (client.in_flight_callbacks == 0) {\n    FinalizeClientLocked(index);\n  }\n}",
        )
    else:
        finalize_client = ""
        submit_frame = extract_snippet(
            norm_src,
            "void AudioSystem::SubmitFrame(size_t index, uint32_t samples_ptr) {",
            "  (clients_[index].driver)->SubmitFrame(samples_ptr);\n}",
        )
        unregister_client = extract_snippet(
            norm_src,
            "void AudioSystem::UnregisterClient(size_t index) {",
            "  assert_true(wait_result == rex::thread::WaitResult::kTimeout);\n}",
        )

    return {
        "clients_struct": clients_struct,
        "worker_dispatch": worker_dispatch,
        "find_free": find_free,
        "shutdown_fn": shutdown_fn,
        "finalize_client": finalize_client,
        "register_client": register_client,
        "submit_frame": submit_frame,
        "unregister_client": unregister_client,
    }


HARNESS_CPP = r"""
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <vector>

// Exact rex_assert semantics from external/rexglue-sdk/include/rex/assert.h:28-33
#ifdef NDEBUG
#define rex_assert(expr) ((void)(false && (expr)))
#else
#include <cassert>
#define rex_assert(expr) assert(expr)
#endif
#define assert_true(expr) rex_assert(expr)
#define assert_not_null(expr) rex_assert((expr) != nullptr)

// Minimal logging / profiler / X_STATUS shims matching ReXGlue signatures
#define REXAPU_DEBUG(...) ((void)0)
#define REXAPU_WARN(...) ((void)0)
#define SCOPE_profile_cpu_i(cat, name) ((void)0)
#define SCOPE_profile_cpu_f(cat) ((void)0)

using X_STATUS = uint32_t;
constexpr X_STATUS X_STATUS_SUCCESS = 0;
constexpr X_STATUS X_STATUS_UNSUCCESSFUL = 0xC0000001u;
inline bool XFAILED(X_STATUS s) { return (s & 0x80000000u) != 0; }

namespace rex {
template <typename T, size_t N>
constexpr size_t countof(T (&)[N]) { return N; }
}  // namespace rex

namespace rex::thread {

enum class WaitResult { kSuccess, kTimeout, kFailed };

class global_critical_region {
 public:
  static std::recursive_mutex& mutex() {
    static std::recursive_mutex m;
    return m;
  }
  inline std::unique_lock<std::recursive_mutex> Acquire() {
    return std::unique_lock<std::recursive_mutex>(mutex());
  }
};

class Event {
 public:
  void Set() {
    std::lock_guard<std::mutex> lk(mu_);
    signaled_ = true;
    cv_.notify_all();
  }
  bool IsSignaled() {
    std::lock_guard<std::mutex> lk(mu_);
    return signaled_;
  }
 private:
  std::mutex mu_;
  std::condition_variable cv_;
  bool signaled_ = false;
};

class Thread {
 public:
  void MarkExited() {
    std::lock_guard<std::mutex> lk(mu_);
    exited_ = true;
    cv_.notify_all();
  }
  WaitResult WaitExit(std::chrono::milliseconds timeout) {
    std::unique_lock<std::mutex> lk(mu_);
    if (cv_.wait_for(lk, timeout, [&] { return exited_; })) {
      return WaitResult::kSuccess;
    }
    return WaitResult::kTimeout;
  }
 private:
  std::mutex mu_;
  std::condition_variable cv_;
  bool exited_ = false;
};

class Semaphore {
 public:
  explicit Semaphore(uint32_t max_count) : count_(0), max_count_(max_count) {}
  bool Release(uint32_t n, uint32_t* prev_out) {
    std::lock_guard<std::mutex> lk(mu_);
    if (prev_out) *prev_out = count_;
    if (count_ + n > max_count_) return false;
    count_ += n;
    cv_.notify_all();
    return true;
  }
  WaitResult TryWait() {
    std::lock_guard<std::mutex> lk(mu_);
    if (count_ > 0) {
      --count_;
      return WaitResult::kSuccess;
    }
    return WaitResult::kTimeout;
  }
  WaitResult WaitBlocking(std::chrono::milliseconds timeout) {
    std::unique_lock<std::mutex> lk(mu_);
    if (!cv_.wait_for(lk, timeout, [&] { return count_ > 0; })) {
      return WaitResult::kTimeout;
    }
    --count_;
    return WaitResult::kSuccess;
  }
  uint32_t count() {
    std::lock_guard<std::mutex> lk(mu_);
    return count_;
  }

 private:
  std::mutex mu_;
  std::condition_variable cv_;
  uint32_t count_;
  uint32_t max_count_;
};

inline WaitResult Wait(Semaphore* sem, bool /*alertable*/, std::chrono::milliseconds timeout) {
  if (timeout.count() == 0) {
    return sem->TryWait();
  }
  return sem->WaitBlocking(timeout);
}

inline WaitResult Wait(Thread* th, bool /*alertable*/, std::chrono::milliseconds timeout) {
  return th ? th->WaitExit(timeout) : WaitResult::kFailed;
}

}  // namespace rex::thread

namespace rex::memory {

template <typename T>
inline void store_and_swap(void* ptr, T val) {
  uint32_t v = static_cast<uint32_t>(val);
  uint32_t swapped = ((v & 0x000000FFu) << 24) | ((v & 0x0000FF00u) << 8) |
                     ((v & 0x00FF0000u) >> 8) | ((v & 0xFF000000u) >> 24);
  std::memcpy(ptr, &swapped, sizeof(swapped));
}

template <typename T>
inline T load_and_swap(const void* ptr) {
  uint32_t raw = 0;
  std::memcpy(&raw, ptr, sizeof(raw));
  return static_cast<T>(((raw & 0x000000FFu) << 24) | ((raw & 0x0000FF00u) << 8) |
                        ((raw & 0x00FF0000u) >> 8) | ((raw & 0xFF000000u) >> 24));
}

// Host-heap-backed guest SystemHeap so ASan detects guest-heap UAF on wrapped_callback_arg.
class Memory {
 public:
  ~Memory() {
    std::lock_guard<std::mutex> lk(mu_);
    for (auto& kv : allocs_) {
      if (kv.second.live) {
        delete[] kv.second.ptr;
      }
    }
  }

  uint32_t SystemHeapAlloc(uint32_t size) {
    std::lock_guard<std::mutex> lk(mu_);
    uint32_t guest_addr = next_addr_;
    next_addr_ += 0x100u;
    uint8_t* raw = new uint8_t[size];
    std::memset(raw, 0, size);
    allocs_[guest_addr] = {raw, true};
    ++total_allocs_;
    ++live_allocs_;
    return guest_addr;
  }

  void SystemHeapFree(uint32_t guest_addr) {
    std::lock_guard<std::mutex> lk(mu_);
    if (guest_addr == 0) {
      ++null_frees_;
      return;
    }
    auto it = allocs_.find(guest_addr);
    if (it == allocs_.end() || !it->second.live) {
      ++double_frees_;
      return;
    }
    delete[] it->second.ptr;
    it->second.live = false;
    ++total_frees_;
    --live_allocs_;
    // Intentionally keep dangling pointer in map to model guest virtual address
    // translation hitting freed storage (ASan catches dereference as heap-use-after-free).
  }

  void* TranslateVirtual(uint32_t guest_addr) {
    std::lock_guard<std::mutex> lk(mu_);
    auto it = allocs_.find(guest_addr);
    return (it != allocs_.end()) ? static_cast<void*>(it->second.ptr) : nullptr;
  }

  size_t total_allocs() { std::lock_guard<std::mutex> lk(mu_); return total_allocs_; }
  size_t total_frees() { std::lock_guard<std::mutex> lk(mu_); return total_frees_; }
  size_t live_allocs() { std::lock_guard<std::mutex> lk(mu_); return live_allocs_; }
  size_t double_frees() { std::lock_guard<std::mutex> lk(mu_); return double_frees_; }

 private:
  struct Entry {
    uint8_t* ptr;
    bool live;
  };
  std::mutex mu_;
  uint32_t next_addr_ = 0x80010000u;
  std::unordered_map<uint32_t, Entry> allocs_;
  size_t total_allocs_ = 0;
  size_t total_frees_ = 0;
  size_t live_allocs_ = 0;
  size_t double_frees_ = 0;
  size_t null_frees_ = 0;
};

}  // namespace rex::memory

namespace rex::audio {

namespace {
constexpr std::chrono::milliseconds kWorkerShutdownTimeout{500};
}  // namespace

class AudioDriver {
 public:
  virtual ~AudioDriver() = default;
  virtual void SubmitFrame(uint32_t samples_ptr) = 0;
};

class MockAudioDriver : public AudioDriver {
 public:
  explicit MockAudioDriver(int id) : id_(id) {}
  void SubmitFrame(uint32_t samples_ptr) override {
    std::lock_guard<std::mutex> lk(mu_);
    received_frames_.push_back(samples_ptr);
  }
  std::vector<uint32_t> frames() {
    std::lock_guard<std::mutex> lk(mu_);
    return received_frames_;
  }
  int id() const { return id_; }

 private:
  int id_;
  std::mutex mu_;
  std::vector<uint32_t> received_frames_;
};

struct DummyThreadState {};
struct DummyWorkerThread {
  DummyThreadState* thread_state() { return &ts_; }
  rex::thread::Thread* thread() { return &host_thread_; }
  void Terminate(int /*code*/) { terminated_ = true; }
  DummyThreadState ts_;
  rex::thread::Thread host_thread_;
  std::atomic<bool> terminated_{false};
};

struct DummyXmaDecoder {
  void Shutdown() { shutdown_called_ = true; }
  std::atomic<bool> shutdown_called_{false};
};

class FunctionDispatcher {
 public:
  using CallbackFn = std::function<void(uint32_t callback_addr, uint64_t arg0)>;
  void SetHandler(CallbackFn fn) { handler_ = std::move(fn); }
  void Execute(DummyThreadState* /*ts*/, uint32_t callback_addr, uint64_t* args, size_t count) {
    if (handler_) {
      handler_(callback_addr, count > 0 ? args[0] : 0);
    }
  }

 private:
  CallbackFn handler_;
};

class AudioSystem {
 public:
  AudioSystem(rex::memory::Memory* mem, FunctionDispatcher* disp)
      : memory_(mem), function_dispatcher_(disp), queued_frames_(8) {
    std::memset(clients_, 0, sizeof(clients_));
    for (size_t i = 0; i < kMaximumClientCount; ++i) {
      client_semaphores_[i] = std::make_unique<rex::thread::Semaphore>(queued_frames_);
    }
    shutdown_event_ = std::make_unique<rex::thread::Event>();
    xma_decoder_ = std::make_unique<DummyXmaDecoder>();
    worker_thread_ = std::make_unique<DummyWorkerThread>();
  }

  rex::memory::Memory* memory() const { return memory_; }

  X_STATUS RegisterClient(uint32_t callback, uint32_t callback_arg, size_t* out_index);
  void SubmitFrame(size_t index, uint32_t samples_ptr);
  void UnregisterClient(size_t index);
  void Shutdown();

  void SetWorkerRunning(bool running) { worker_running_ = running; }
  void MarkWorkerExited() {
    if (worker_thread_) worker_thread_->host_thread_.MarkExited();
  }
  bool IsShutdownEventSignaled() const { return shutdown_event_->IsSignaled(); }

  // Drives one verbatim WorkerThreadMain dispatch iteration for a signaled client index.
  bool PumpOneClient(size_t index) {
    uint32_t diag_pump_count = 0;
    bool pumped = false;
    if (client_semaphores_[index]->WaitBlocking(std::chrono::milliseconds(2000)) !=
        rex::thread::WaitResult::kSuccess) {
      return false;
    }
    {
      // --- BEGIN VERBATIM EXTRACTED WorkerThreadMain DISPATCH BLOCK ---
__WORKER_DISPATCH__
      // --- END VERBATIM EXTRACTED WorkerThreadMain DISPATCH BLOCK ---
    }
    return pumped;
  }

  MockAudioDriver* last_created_driver() const { return last_created_driver_; }
  size_t drivers_created() const { return drivers_created_; }
  size_t drivers_destroyed() const { return drivers_destroyed_; }
  size_t null_driver_destroys() const { return null_driver_destroys_; }
  size_t double_driver_destroys() const { return double_driver_destroys_; }
  size_t live_driver_count() const { return live_drivers_.size(); }

  static constexpr size_t kMaximumClientCount = 8;

 private:
  int FindFreeClient();
__FINALIZE_DECL__

  X_STATUS CreateDriver(size_t /*index*/, rex::thread::Semaphore* /*semaphore*/, AudioDriver** out_driver) {
    auto* drv = new MockAudioDriver(++next_driver_id_);
    live_drivers_.insert(drv);
    ++drivers_created_;
    last_created_driver_ = drv;
    *out_driver = drv;
    return X_STATUS_SUCCESS;
  }

  void DestroyDriver(AudioDriver* driver) {
    if (!driver) {
      ++null_driver_destroys_;
      return;
    }
    auto it = live_drivers_.find(driver);
    if (it == live_drivers_.end()) {
      ++double_driver_destroys_;
      return;
    }
    live_drivers_.erase(it);
    ++drivers_destroyed_;
    if (driver == last_created_driver_) {
      last_created_driver_ = nullptr;
    }
    delete driver;
  }

  rex::memory::Memory* memory_ = nullptr;
  FunctionDispatcher* function_dispatcher_ = nullptr;
  std::unique_ptr<DummyXmaDecoder> xma_decoder_;
  uint32_t queued_frames_ = 8;
  std::atomic<bool> worker_running_{false};
  std::unique_ptr<DummyWorkerThread> worker_thread_;
  std::unique_ptr<rex::thread::Event> shutdown_event_;

  rex::thread::global_critical_region global_critical_region_;
  // --- BEGIN VERBATIM EXTRACTED clients_ STRUCT ---
__CLIENTS_STRUCT__
  // --- END VERBATIM EXTRACTED clients_ STRUCT ---
  std::unique_ptr<rex::thread::Semaphore> client_semaphores_[kMaximumClientCount];

  int next_driver_id_ = 0;
  MockAudioDriver* last_created_driver_ = nullptr;
  std::unordered_set<AudioDriver*> live_drivers_;
  size_t drivers_created_ = 0;
  size_t drivers_destroyed_ = 0;
  size_t null_driver_destroys_ = 0;
  size_t double_driver_destroys_ = 0;
};

// --- BEGIN VERBATIM EXTRACTED AudioSystem METHODS ---
__FIND_FREE__

__SHUTDOWN_FN__

__FINALIZE_CLIENT__

__REGISTER_CLIENT__

__SUBMIT_FRAME__

__UNREGISTER_CLIENT__
// --- END VERBATIM EXTRACTED AudioSystem METHODS ---

}  // namespace rex::audio

struct Barrier {
  std::mutex mu;
  std::condition_variable cv;
  bool flag = false;
  void Signal() {
    std::lock_guard<std::mutex> lk(mu);
    flag = true;
    cv.notify_all();
  }
  bool Wait(int timeout_ms = 5000) {
    std::unique_lock<std::mutex> lk(mu);
    return cv.wait_for(lk, std::chrono::milliseconds(timeout_ms), [&] { return flag; });
  }
};

static bool verify_clean_accounting(rex::audio::AudioSystem& audio, rex::memory::Memory& mem, const char* tag) {
  if (audio.drivers_created() != audio.drivers_destroyed() ||
      audio.live_driver_count() != 0 ||
      audio.null_driver_destroys() != 0 ||
      audio.double_driver_destroys() != 0) {
    std::fprintf(stderr, "%s: driver accounting mismatch created=%zu destroyed=%zu live=%zu null=%zu dbl=%zu\n",
                 tag, audio.drivers_created(), audio.drivers_destroyed(), audio.live_driver_count(),
                 audio.null_driver_destroys(), audio.double_driver_destroys());
    return false;
  }
  if (mem.total_allocs() != mem.total_frees() ||
      mem.live_allocs() != 0 ||
      mem.double_frees() != 0) {
    std::fprintf(stderr, "%s: mem accounting mismatch allocs=%zu frees=%zu live=%zu dbl=%zu\n",
                 tag, mem.total_allocs(), mem.total_frees(), mem.live_allocs(), mem.double_frees());
    return false;
  }
  return true;
}

int main(int argc, char** argv) {
  if (argc < 2) {
    std::fprintf(stderr, "Usage: %s <mode>\n", argv[0]);
    return 2;
  }
  std::string mode = argv[1];

  rex::memory::Memory mem;
  rex::audio::FunctionDispatcher disp;
  rex::audio::AudioSystem audio(&mem, &disp);

  constexpr uint32_t kCallbackA = 0x824C2800u;
  constexpr uint32_t kArgA = 0x400B0570u;
  constexpr uint32_t kSamplesA = 0x82B94C20u;
  constexpr uint32_t kCallbackB = 0x824C2900u;
  constexpr uint32_t kArgB = 0x400B05D0u;
  constexpr uint32_t kSamplesB = 0x82B95000u;

  if (mode == "safe_ordering") {
    Barrier callback_done;
    size_t idx = 99;
    if (audio.RegisterClient(kCallbackA, kArgA, &idx) != X_STATUS_SUCCESS || idx != 0) {
      std::fprintf(stderr, "RegisterClient failed\n");
      return 3;
    }
    auto* drvA = audio.last_created_driver();
    uint32_t observed_arg = 0;

    disp.SetHandler([&](uint32_t cb, uint64_t wrapped_ptr) {
      if (cb != kCallbackA) std::abort();
      observed_arg = rex::memory::load_and_swap<uint32_t>(
          mem.TranslateVirtual(static_cast<uint32_t>(wrapped_ptr)));
      audio.SubmitFrame(idx, kSamplesA);
      callback_done.Signal();
    });

    std::thread worker([&] { audio.PumpOneClient(idx); });
    if (!callback_done.Wait()) std::abort();
    worker.join();

    auto frames = drvA->frames();
    audio.UnregisterClient(idx);
    if (frames.size() != 1 || frames[0] != kSamplesA || observed_arg != kArgA) {
      std::fprintf(stderr, "Unexpected safe_ordering state\n");
      return 4;
    }
    if (!verify_clean_accounting(audio, mem, "safe_ordering")) return 5;
    std::printf("SAFE_ORDERING_PASS frames=%zu samples=0x%08X arg=0x%08X\n",
                frames.size(), frames[0], observed_arg);
    return 0;
  }

  if (mode == "hazard_a_null_deref") {
    Barrier worker_in_callback;
    Barrier unregister_done;
    size_t idx = 99;
    audio.RegisterClient(kCallbackA, kArgA, &idx);

    disp.SetHandler([&](uint32_t /*cb*/, uint64_t /*wrapped_ptr*/) {
      worker_in_callback.Signal();
      if (!unregister_done.Wait()) std::abort();
      audio.SubmitFrame(idx, kSamplesA);
    });

    std::thread worker([&] { audio.PumpOneClient(idx); });
    if (!worker_in_callback.Wait()) std::abort();
    audio.UnregisterClient(idx);
    unregister_done.Signal();
    worker.join();
    if (!verify_clean_accounting(audio, mem, "hazard_a_null_deref")) return 5;
    std::printf("HAZARD_A_SAFE_PASS\n");
    return 0;
  }

  if (mode == "hazard_b_wrapped_arg_uaf") {
    Barrier worker_in_callback;
    Barrier unregister_done;
    size_t idx = 99;
    uint32_t observed_arg = 0;
    audio.RegisterClient(kCallbackA, kArgA, &idx);

    disp.SetHandler([&](uint32_t /*cb*/, uint64_t wrapped_ptr) {
      worker_in_callback.Signal();
      if (!unregister_done.Wait()) std::abort();
      observed_arg = rex::memory::load_and_swap<uint32_t>(
          mem.TranslateVirtual(static_cast<uint32_t>(wrapped_ptr)));
    });

    std::thread worker([&] { audio.PumpOneClient(idx); });
    if (!worker_in_callback.Wait()) std::abort();
    audio.UnregisterClient(idx);
    unregister_done.Signal();
    worker.join();
    if (observed_arg != kArgA) {
      std::fprintf(stderr, "Unexpected arg 0x%08X != 0x%08X\n", observed_arg, kArgA);
      return 4;
    }
    if (!verify_clean_accounting(audio, mem, "hazard_b_wrapped_arg_uaf")) return 5;
    std::printf("HAZARD_B_SAFE_PASS arg=0x%08X\n", observed_arg);
    return 0;
  }

  if (mode == "hazard_c_slot_reuse_aba") {
    Barrier worker_in_callback;
    Barrier reregister_done;
    size_t idxA = 99;
    audio.RegisterClient(kCallbackA, kArgA, &idxA);

    disp.SetHandler([&](uint32_t cb, uint64_t /*wrapped_ptr*/) {
      if (cb == kCallbackA) {
        worker_in_callback.Signal();
        if (!reregister_done.Wait()) std::abort();
        audio.SubmitFrame(idxA, kSamplesA);
      } else if (cb == kCallbackB) {
        audio.SubmitFrame(1, kSamplesB);
      }
    });

    std::thread workerA([&] { audio.PumpOneClient(idxA); });
    if (!worker_in_callback.Wait()) std::abort();

    audio.UnregisterClient(idxA);
    size_t idxB = 99;
    if (audio.RegisterClient(kCallbackB, kArgB, &idxB) != X_STATUS_SUCCESS) {
      std::fprintf(stderr, "RegisterClient B failed\n");
      return 3;
    }
    auto* drvB = audio.last_created_driver();
    int drvB_id = drvB->id();
    reregister_done.Signal();
    workerA.join();

    auto framesB_after_A = drvB->frames();
    if (idxB == idxA && framesB_after_A.size() == 1 && framesB_after_A[0] == kSamplesA) {
      audio.UnregisterClient(idxB);
      std::printf("HAZARD_C_ABA_REPRODUCED slot=%zu client_a_frame=0x%08X delivered_to_client_b_driver_id=%d\n",
                  idxB, framesB_after_A[0], drvB_id);
      return 42;
    }

    // Patched path: slot 0 stayed reserved until workerA finished, so Client B got slot 1
    // and Client A's stale SubmitFrame(0, ...) was dropped without reaching drvB.
    if (idxB == idxA || !framesB_after_A.empty()) {
      std::fprintf(stderr, "Unexpected ABA state idxA=%zu idxB=%zu framesB=%zu\n",
                   idxA, idxB, framesB_after_A.size());
      return 4;
    }
    // Verify Client B works normally and slot 0 is now reclaimed for a new Client C.
    std::thread workerB([&] { audio.PumpOneClient(idxB); });
    workerB.join();
    auto framesB_final = drvB->frames();
    size_t idxC = 99;
    audio.RegisterClient(kCallbackA, kArgA, &idxC);
    audio.UnregisterClient(idxB);
    audio.UnregisterClient(idxC);
    if (framesB_final.size() != 1 || framesB_final[0] != kSamplesB || idxC != idxA) {
      std::fprintf(stderr, "Unexpected slot reclamation idxC=%zu framesB=%zu\n",
                   idxC, framesB_final.size());
      return 5;
    }
    if (!verify_clean_accounting(audio, mem, "hazard_c_slot_reuse_aba")) return 6;
    std::printf("HAZARD_C_SAFE_PASS idxA=%zu idxB=%zu idxC_reclaimed=%zu\n", idxA, idxB, idxC);
    return 0;
  }

  if (mode == "self_unregister") {
    size_t idx = 99;
    uint32_t observed_arg = 0;
    audio.RegisterClient(kCallbackA, kArgA, &idx);

    disp.SetHandler([&](uint32_t /*cb*/, uint64_t wrapped_ptr) {
      // Re-entrant self-unregister from inside the worker callback!
      audio.UnregisterClient(idx);
      // Second unregister must be an idempotent no-op.
      audio.UnregisterClient(idx);
      // Reading wrapped_callback_arg after self-unregister must not UAF.
      observed_arg = rex::memory::load_and_swap<uint32_t>(
          mem.TranslateVirtual(static_cast<uint32_t>(wrapped_ptr)));
      // Submitting a frame after self-unregister must be a safe no-op.
      audio.SubmitFrame(idx, kSamplesA);
    });

    std::thread worker([&] { audio.PumpOneClient(idx); });
    worker.join();
    if (observed_arg != kArgA) {
      std::fprintf(stderr, "self_unregister arg mismatch 0x%08X\n", observed_arg);
      return 4;
    }
    if (!verify_clean_accounting(audio, mem, "self_unregister")) return 5;
    std::printf("SELF_UNREGISTER_PASS arg=0x%08X\n", observed_arg);
    return 0;
  }

  if (mode == "multiple_clients") {
    size_t idx0 = 99, idx1 = 99;
    audio.RegisterClient(kCallbackA, kArgA, &idx0);
    auto* drv0 = audio.last_created_driver();
    audio.RegisterClient(kCallbackB, kArgB, &idx1);
    auto* drv1 = audio.last_created_driver();

    disp.SetHandler([&](uint32_t cb, uint64_t /*wrapped_ptr*/) {
      if (cb == kCallbackA) {
        audio.SubmitFrame(idx0, kSamplesA);
      } else if (cb == kCallbackB) {
        audio.SubmitFrame(idx1, kSamplesB);
      }
    });

    std::thread worker([&] {
      audio.PumpOneClient(idx0);
      audio.PumpOneClient(idx1);
    });
    worker.join();

    auto f1 = drv1->frames();
    audio.UnregisterClient(idx1);

    // Client 0 continues pumping after Client 1 is unregistered (Rayman 3 HD movie-end pattern).
    std::thread worker2([&] { audio.PumpOneClient(idx0); });
    worker2.join();
    auto f0 = drv0->frames();
    audio.UnregisterClient(idx0);

    if (idx0 != 0 || idx1 != 1 || f1.size() != 1 || f1[0] != kSamplesB ||
        f0.size() != 2 || f0[0] != kSamplesA || f0[1] != kSamplesA) {
      std::fprintf(stderr, "multiple_clients mismatch f0=%zu f1=%zu\n", f0.size(), f1.size());
      return 4;
    }
    if (!verify_clean_accounting(audio, mem, "multiple_clients")) return 5;
    std::printf("MULTIPLE_CLIENTS_PASS f0=%zu f1=%zu\n", f0.size(), f1.size());
    return 0;
  }

  if (mode == "shutdown_in_flight") {
    // Models Shutdown() called while a callback is in flight on the worker thread.
    // On unpatched code, Shutdown() does NOT acquire global_critical_region_ and if
    // worker_running_ is false or worker exits/races, we test both:
    // Here worker_running_ = true; Shutdown() signals shutdown_event_ and waits for
    // worker_thread_ to exit (which happens right after callback finishes), then
    // cleans up remaining clients under global_critical_region_.
    // To also demonstrate the unpatched race when Shutdown() runs concurrently with an
    // active callback that outlives the timeout, we check whether Shutdown() cleans up
    // while callback reads wrapped_callback_arg.
    Barrier worker_in_callback;
    Barrier allow_callback_finish;
    size_t idx0 = 99, idx1 = 99;
    audio.SetWorkerRunning(true);
    audio.RegisterClient(kCallbackA, kArgA, &idx0);
    audio.RegisterClient(kCallbackB, kArgB, &idx1);
    uint32_t observed_arg = 0;

    disp.SetHandler([&](uint32_t /*cb*/, uint64_t wrapped_ptr) {
      worker_in_callback.Signal();
      // Wait for Shutdown() to signal shutdown_event_ (deterministic, no sleep).
      if (!allow_callback_finish.Wait()) std::abort();
      observed_arg = rex::memory::load_and_swap<uint32_t>(
          mem.TranslateVirtual(static_cast<uint32_t>(wrapped_ptr)));
      audio.SubmitFrame(idx0, kSamplesA);
    });

    std::thread worker([&] {
      audio.PumpOneClient(idx0);
      audio.MarkWorkerExited();
    });
    if (!worker_in_callback.Wait()) std::abort();

    // Unregister client 0 while its callback is in flight, then initiate Shutdown().
    audio.UnregisterClient(idx0);
    std::thread shutdown_thr([&] { audio.Shutdown(); });

    // Wait deterministically until Shutdown() has signaled shutdown_event_ (busy-poll with yield).
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
    while (!audio.IsShutdownEventSignaled() && std::chrono::steady_clock::now() < deadline) {
      std::this_thread::yield();
    }
    allow_callback_finish.Signal();
    worker.join();
    shutdown_thr.join();

    if (observed_arg != kArgA) {
      std::fprintf(stderr, "shutdown_in_flight arg mismatch 0x%08X\n", observed_arg);
      return 4;
    }
    if (!verify_clean_accounting(audio, mem, "shutdown_in_flight")) return 5;
    std::printf("SHUTDOWN_IN_FLIGHT_PASS arg=0x%08X\n", observed_arg);
    return 0;
  }

  if (mode == "repeated_register_unregister") {
    // 24 register/pump/unregister cycles + 8-slot exhaustion + full reclamation.
    for (int cycle = 0; cycle < 24; ++cycle) {
      size_t idx = 99;
      if (audio.RegisterClient(kCallbackA, kArgA + static_cast<uint32_t>(cycle), &idx) != X_STATUS_SUCCESS) {
        std::fprintf(stderr, "Cycle %d RegisterClient failed\n", cycle);
        return 3;
      }
      disp.SetHandler([&](uint32_t /*cb*/, uint64_t wrapped_ptr) {
        uint32_t v = rex::memory::load_and_swap<uint32_t>(
            mem.TranslateVirtual(static_cast<uint32_t>(wrapped_ptr)));
        if (v != kArgA + static_cast<uint32_t>(cycle)) std::abort();
        audio.SubmitFrame(idx, kSamplesA);
      });
      std::thread w([&] { audio.PumpOneClient(idx); });
      w.join();
      audio.UnregisterClient(idx);
    }

    // Verify all 8 slots are available (no slot leaks).
    size_t slots[rex::audio::AudioSystem::kMaximumClientCount];
    for (size_t i = 0; i < rex::audio::AudioSystem::kMaximumClientCount; ++i) {
      if (audio.RegisterClient(kCallbackA, kArgA, &slots[i]) != X_STATUS_SUCCESS) {
        std::fprintf(stderr, "Slot %zu unavailable (slot leak)\n", i);
        return 4;
      }
    }
#ifdef G6P109_PATCHED
    // 9th simultaneous RegisterClient must fail cleanly without crashing/asserting.
    size_t overflow_idx = 99;
    if (audio.RegisterClient(kCallbackA, kArgA, &overflow_idx) != X_STATUS_UNSUCCESSFUL) {
      std::fprintf(stderr, "Expected X_STATUS_UNSUCCESSFUL on 9th client\n");
      return 5;
    }
    // Out-of-bounds SubmitFrame / UnregisterClient must be safe no-ops.
    audio.SubmitFrame(99, kSamplesA);
    audio.UnregisterClient(99);
#endif
    for (size_t i = 0; i < rex::audio::AudioSystem::kMaximumClientCount; ++i) {
      audio.UnregisterClient(slots[i]);
    }
    if (!verify_clean_accounting(audio, mem, "repeated_register_unregister")) return 6;
    std::printf("REPEATED_CYCLES_PASS cycles=24 slots=8\n");
    return 0;
  }

  if (mode == "exception_unwind") {
    Barrier worker_in_callback;
    Barrier unregister_done;
    size_t idx = 99;
    audio.RegisterClient(kCallbackA, kArgA, &idx);

    disp.SetHandler([&](uint32_t /*cb*/, uint64_t /*wrapped_ptr*/) {
      worker_in_callback.Signal();
      if (!unregister_done.Wait()) std::abort();
      throw std::runtime_error("simulated_guest_callback_abort");
    });

    bool caught = false;
    std::thread worker([&] {
      try {
        audio.PumpOneClient(idx);
      } catch (const std::runtime_error&) {
        caught = true;
      }
    });
    if (!worker_in_callback.Wait()) std::abort();
    audio.UnregisterClient(idx);
    unregister_done.Signal();
    worker.join();

    if (!caught) {
      std::fprintf(stderr, "Expected exception to propagate\n");
      return 4;
    }
    // Slot must be reclaimed even after exception unwind!
    size_t idx2 = 99;
    if (audio.RegisterClient(kCallbackB, kArgB, &idx2) != X_STATUS_SUCCESS || idx2 != idx) {
      std::fprintf(stderr, "Slot not reclaimed after unwind idx=%zu idx2=%zu\n", idx, idx2);
      return 5;
    }
    audio.UnregisterClient(idx2);
    if (!verify_clean_accounting(audio, mem, "exception_unwind")) return 6;
    std::printf("EXCEPTION_UNWIND_PASS reclaimed_slot=%zu\n", idx2);
    return 0;
  }

  std::fprintf(stderr, "Unknown mode: %s\n", mode.c_str());
  return 2;
}
"""


def build_harness_source(src_text: str, hdr_text: str, patched: bool) -> str:
    methods = extract_audio_system_methods(src_text, hdr_text, patched=patched)
    finalize_decl = "  void FinalizeClientLocked(size_t index);" if patched else ""
    return (
        HARNESS_CPP.replace("__CLIENTS_STRUCT__", methods["clients_struct"])
        .replace("__WORKER_DISPATCH__", methods["worker_dispatch"])
        .replace("__FIND_FREE__", methods["find_free"])
        .replace("__SHUTDOWN_FN__", methods["shutdown_fn"])
        .replace("__FINALIZE_DECL__", finalize_decl)
        .replace("__FINALIZE_CLIENT__", methods["finalize_client"])
        .replace("__REGISTER_CLIENT__", methods["register_client"])
        .replace("__SUBMIT_FRAME__", methods["submit_frame"])
        .replace("__UNREGISTER_CLIENT__", methods["unregister_client"])
    )


def compile_asan_harness(
    cpp_source: str, build_dir: Path, name: str, debug_asserts: bool, patched: bool
) -> Path:
    src_path = build_dir / f"{name}.cpp"
    exe_path = build_dir / f"{name}.exe"
    src_path.write_text(cpp_source, encoding="utf-8")

    llvm_bin = os.environ.get("R3HD_LLVM_BIN", DEFAULT_LLVM_BIN)
    vcvars = os.environ.get("R3HD_VCVARS", DEFAULT_VCVARS)
    clangxx = Path(llvm_bin) / "clang++.exe"
    if not clangxx.exists():
        raise RuntimeError(f"clang++.exe not found at {clangxx}")
    if not Path(vcvars).exists():
        raise RuntimeError(f"vcvars64.bat not found at {vcvars}")

    flags = ["-std=c++20", "-O1", "-g", "-fsanitize=address", "-fno-omit-frame-pointer"]
    if not debug_asserts:
        flags.append("-DNDEBUG")
    if patched:
        flags.append("-DG6P109_PATCHED")

    if os.environ.get("LIB") and os.environ.get("INCLUDE"):
        proc = subprocess.run(
            [str(clangxx), *flags, str(src_path), "-o", str(exe_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    else:
        bat = build_dir / f"build_{name}.bat"
        flag_str = " ".join(flags)
        bat.write_text(
            f"@echo off\r\n"
            f'call "{vcvars}" >nul 2>&1\r\n'
            f"if errorlevel 1 exit /b 2\r\n"
            f'"{clangxx}" {flag_str} "{src_path}" -o "{exe_path}"\r\n',
            encoding="utf-8",
        )
        proc = subprocess.run(["cmd", "/c", str(bat)], capture_output=True, text=True, timeout=60)

    if proc.returncode != 0:
        raise RuntimeError(
            f"clang++ ASan compile failed ({name}, rc={proc.returncode}):\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return exe_path


def run_mode(exe_path: Path, mode: str) -> subprocess.CompletedProcess[str]:
    llvm_bin = os.environ.get("R3HD_LLVM_BIN", DEFAULT_LLVM_BIN)
    env = os.environ.copy()
    extra_paths = [llvm_bin]
    llvm_root = Path(llvm_bin).parent
    for dll in llvm_root.glob("lib/clang/*/lib/windows/clang_rt.asan_dynamic-x86_64.dll"):
        extra_paths.append(str(dll.parent))
    env["PATH"] = ";".join(extra_paths) + ";" + env.get("PATH", "")
    env["ASAN_OPTIONS"] = "detect_leaks=0:halt_on_error=1:abort_on_error=0"
    return subprocess.run(
        [str(exe_path), mode],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )


def run_selftest() -> int:
    pinned_h = subprocess.check_output(
        ["git", "-C", str(SDK), "show", f"{EXPECTED_SDK_PIN}:include/rex/audio/audio_system.h"],
        text=True,
        errors="replace",
    )
    pinned_cpp = subprocess.check_output(
        ["git", "-C", str(SDK), "show", f"{EXPECTED_SDK_PIN}:src/audio/audio_system.cpp"],
        text=True,
        errors="replace",
    )
    unpatched = extract_audio_system_methods(pinned_cpp, pinned_h, patched=False)
    patched_h, h_st = patch_mod.apply_header_text(pinned_h)
    patched_cpp, cpp_st = patch_mod.apply_source_text(pinned_cpp)
    patched = extract_audio_system_methods(patched_cpp, patched_h, patched=True)

    checks = {
        "selftest extracts unpatched WorkerThreadMain dispatch block": "global_lock.unlock();" in unpatched["worker_dispatch"],
        "selftest extracts unpatched SubmitFrame body": "(clients_[index].driver)->SubmitFrame(samples_ptr);" in unpatched["submit_frame"],
        "selftest applies G6-P109 patch cleanly in memory": h_st == "patched" and cpp_st == "patched",
        "selftest extracts patched FinalizeClientLocked & InFlightCallbackGuard": (
            "InFlightCallbackGuard" in patched["worker_dispatch"]
            and "FinalizeClientLocked" in patched["finalize_client"]
        ),
    }
    try:
        extract_audio_system_methods("", "", patched=False)
        checks["selftest rejects empty source"] = False
    except RuntimeError:
        checks["selftest rejects empty source"] = True

    ok = all(checks.values())
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print(f"G6P108_SELFTEST {'PASS' if ok else 'FAIL'} {sum(checks.values())}/{len(checks)}")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return run_selftest()

    results: dict[str, bool] = {}

    def check(name: str, cond: bool) -> None:
        results[name] = bool(cond)
        print(f"{'PASS' if cond else 'FAIL'} {name}")

    # 1. Pin, patch-chain, idempotency, and drift-detection verification
    sdk_head = subprocess.check_output(
        ["git", "-C", str(SDK), "rev-parse", "HEAD"], text=True
    ).strip()
    check("SDK pin matches c94f5eb", sdk_head == EXPECTED_SDK_PIN)

    pinned_h = subprocess.check_output(
        ["git", "-C", str(SDK), "show", f"{EXPECTED_SDK_PIN}:include/rex/audio/audio_system.h"],
        text=True,
        errors="replace",
    )
    pinned_cpp = subprocess.check_output(
        ["git", "-C", str(SDK), "show", f"{EXPECTED_SDK_PIN}:src/audio/audio_system.cpp"],
        text=True,
        errors="replace",
    )
    working_h = read_text(AUDIO_SYSTEM_H)
    working_cpp = read_text(AUDIO_SYSTEM_CPP)

    patched_h_mem, h_st1 = patch_mod.apply_header_text(pinned_h)
    _, h_st2 = patch_mod.apply_header_text(patched_h_mem)
    patched_cpp_mem, cpp_st1 = patch_mod.apply_source_text(pinned_cpp)
    _, cpp_st2 = patch_mod.apply_source_text(patched_cpp_mem)
    check(
        "G6-P109 patch applies cleanly to pinned c94f5eb and is idempotent",
        h_st1 == "patched" and h_st2 == "already_applied"
        and cpp_st1 == "patched" and cpp_st2 == "already_applied",
    )
    check(
        "Working-tree audio_system.h and audio_system.cpp match patched output exactly (LF preserved)",
        working_h == patched_h_mem
        and working_cpp == patched_cpp_mem
        and b"\r\n" not in AUDIO_SYSTEM_H.read_bytes()
        and b"\r\n" not in AUDIO_SYSTEM_CPP.read_bytes(),
    )

    drift_missing = False
    try:
        patch_mod.apply_source_text("unrelated file content\n")
    except RuntimeError:
        drift_missing = True
    check("Source drift (missing anchor) raises RuntimeError", drift_missing)

    drift_dup = False
    try:
        patch_mod.apply_header_text(pinned_h + "\n" + patch_mod.H_EDITS[0][1])
    except RuntimeError:
        drift_dup = True
    check("Source drift (duplicate anchor) raises RuntimeError", drift_dup)

    drift_partial = False
    try:
        # Apply only the first hunk of CPP_EDITS to simulate partial drift
        partial_cpp = pinned_cpp.replace(patch_mod.CPP_EDITS[0][1], patch_mod.CPP_EDITS[0][2], 1)
        patch_mod.apply_source_text(partial_cpp)
    except RuntimeError:
        drift_partial = True
    check("Source drift (partial patch) raises RuntimeError", drift_partial)

    bat_text = (ROOT / "tools" / "build_milestone8.bat").read_text(encoding="utf-8")
    p_line = r"python tools\g6p109_audio_client_lifetime_patch.py || exit /b 1"
    r_line = r"python tools\g6p108_audio_client_lifetime_regression.py || exit /b 1"
    check(
        "build_milestone8.bat applies g6p109 patch once before cmake -S external",
        bat_text.count(p_line) == 1 and bat_text.index(p_line) < bat_text.index("cmake -S external"),
    )
    check(
        "build_milestone8.bat runs g6p108/g6p109 regression once before M8_BUILD_OK",
        bat_text.count(r_line) == 1 and bat_text.index(r_line) < bat_text.index("echo M8_BUILD_OK"),
    )

    assert_h = read_text(ASSERT_H)
    check(
        "NDEBUG compiles rex_assert / assert_true1 out to a no-op",
        "#ifdef NDEBUG" in assert_h and "#define rex_assert(expr) ((void)(false && (expr)))" in assert_h,
    )

    krnl_audio = read_text(XBOXKRNL_AUDIO_CPP)
    check(
        "Guest-visible XAudio handle encoding (0x41550000 | index) is preserved",
        "*driver_ptr = 0x41550000 | (static_cast<uint32_t>(index) & 0x0000FFFF);" in krnl_audio
        and "audio_system->UnregisterClient(driver_ptr.guest_address() & 0x0000FFFF);" in krnl_audio,
    )

    # 2. Verbatim source-extracted C++20 ASan harnesses (Unpatched Release, Patched Release, Patched Debug)
    unpatched_src = build_harness_source(pinned_cpp, pinned_h, patched=False)
    patched_src = build_harness_source(working_cpp, working_h, patched=True)

    with tempfile.TemporaryDirectory(prefix="g6p109_audio_repro_") as td:
        tmp = Path(td)
        exe_unpatched = compile_asan_harness(
            unpatched_src, tmp, "unpatched_release", debug_asserts=False, patched=False
        )
        exe_patched_rel = compile_asan_harness(
            patched_src, tmp, "patched_release", debug_asserts=False, patched=True
        )
        exe_patched_dbg = compile_asan_harness(
            patched_src, tmp, "patched_debug", debug_asserts=True, patched=True
        )

        # --- Unpatched Release (-DNDEBUG) Negative & Baseline Controls ---
        r = run_mode(exe_unpatched, "safe_ordering")
        check(
            "Unpatched Release: safe_ordering PASS (rc 0)",
            r.returncode == 0 and "SAFE_ORDERING_PASS" in r.stdout and "AddressSanitizer" not in r.stderr,
        )

        r = run_mode(exe_unpatched, "hazard_a_null_deref")
        comb = r.stdout + "\n" + r.stderr
        check(
            "Unpatched Release (Negative control): Hazard A NULL deref (0x000000000000)",
            r.returncode != 0 and (
                "AddressSanitizer: access-violation on unknown address 0x000000000000" in comb
                or "AddressSanitizer: SEGV on unknown address 0x000000000000" in comb
            ),
        )

        r = run_mode(exe_unpatched, "hazard_b_wrapped_arg_uaf")
        comb = r.stdout + "\n" + r.stderr
        check(
            "Unpatched Release (Negative control): Hazard B wrapped_callback_arg ASan UAF",
            r.returncode != 0 and "AddressSanitizer: heap-use-after-free" in comb,
        )

        r = run_mode(exe_unpatched, "hazard_c_slot_reuse_aba")
        check(
            "Unpatched Release (Negative control): Hazard C slot-reuse ABA misdelivery (rc 42)",
            r.returncode == 42 and "HAZARD_C_ABA_REPRODUCED" in r.stdout,
        )

        r = run_mode(exe_unpatched, "self_unregister")
        comb = r.stdout + "\n" + r.stderr
        check(
            "Unpatched Release (Negative control): callback self-unregister faults (ASan UAF)",
            r.returncode != 0 and "AddressSanitizer: heap-use-after-free" in comb,
        )

        r = run_mode(exe_unpatched, "multiple_clients")
        check(
            "Unpatched Release: multiple_clients baseline PASS (rc 0)",
            r.returncode == 0 and "MULTIPLE_CLIENTS_PASS" in r.stdout and "AddressSanitizer" not in r.stderr,
        )

        r = run_mode(exe_unpatched, "shutdown_in_flight")
        comb = r.stdout + "\n" + r.stderr
        check(
            "Unpatched Release (Negative control): shutdown with callback in flight faults (ASan UAF)",
            r.returncode != 0 and "AddressSanitizer: heap-use-after-free" in comb,
        )

        r = run_mode(exe_unpatched, "repeated_register_unregister")
        check(
            "Unpatched Release: repeated_register_unregister baseline PASS (rc 0)",
            r.returncode == 0 and "REPEATED_CYCLES_PASS" in r.stdout and "AddressSanitizer" not in r.stderr,
        )

        # --- Patched Release (-DNDEBUG) & Patched Debug (assertions enabled) ---
        patched_modes = [
            ("safe_ordering", "SAFE_ORDERING_PASS"),
            ("hazard_a_null_deref", "HAZARD_A_SAFE_PASS"),
            ("hazard_b_wrapped_arg_uaf", "HAZARD_B_SAFE_PASS"),
            ("hazard_c_slot_reuse_aba", "HAZARD_C_SAFE_PASS"),
            ("self_unregister", "SELF_UNREGISTER_PASS"),
            ("multiple_clients", "MULTIPLE_CLIENTS_PASS"),
            ("shutdown_in_flight", "SHUTDOWN_IN_FLIGHT_PASS"),
            ("repeated_register_unregister", "REPEATED_CYCLES_PASS"),
            ("exception_unwind", "EXCEPTION_UNWIND_PASS"),
        ]

        for label, exe in [("Patched Release (-DNDEBUG)", exe_patched_rel), ("Patched Debug (asserts on)", exe_patched_dbg)]:
            for mode, marker in patched_modes:
                r = run_mode(exe, mode)
                ok_mode = (
                    r.returncode == 0
                    and marker in r.stdout
                    and "AddressSanitizer" not in r.stderr
                    and "AddressSanitizer" not in r.stdout
                )
                check(f"{label}: {mode} PASS (0 ASan, exact 1x teardown)", ok_mode)
                if not ok_mode:
                    print(f"  [diag {label} {mode}] rc={r.returncode}\n  STDOUT: {r.stdout.strip()}\n  STDERR: {r.stderr.strip()}")

    passed = sum(results.values())
    total = len(results)
    ok = passed == total
    print(f"G6P108_AUDIO_CLIENT_LIFETIME_REGRESSION {'PASS' if ok else 'FAIL'} {passed}/{total}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
