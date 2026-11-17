// Linux Runtime Bootstrap (LRB): opt-in bring-up of the real ReXGlue memory
// system under a project-owned signal owner. No game data, no generated game
// code, no production runtime replacement. See README.md for the contract.
//
// Lifecycle (process-exclusive, single participating thread, quiescent):
//   Preflight -> Memory::Initialize (SDK installs its SIGSEGV/SIGILL thunk)
//   -> layout/shared-memory ownership verification -> SDK thunk Uninstall
//   (MMIOHandler singleton and ranges retained) -> exclusive LRB owner install
//   -> per-thread attach + owned guest scratch -> ... -> scratch release ->
//   detach -> owner uninstall -> Memory destruction -> residue verification.
//
// Checked-access recovery is NOT general generated-code recovery: exactly one
// admitted fault per checked 32-bit access, one deferred ordinary-code SDK
// dispatch, at most one fresh access. Anything else is terminal.
#pragma once

#include <cstddef>
#include <cstdint>
#include <exception>
#include <memory>
#include <string>
#include <vector>

#include <rex/exception_handler.h>
#include <rex/system/mmio_handler.h>
#include <rex/system/xmemory.h>

#if defined(__linux__) && defined(__x86_64__) && !defined(LRB_ORDINARY_ONLY)
#define LRB_NATIVE 1
#include <signal.h>
#else
#define LRB_NATIVE 0
#endif

namespace lrb {

// Fixed guest layout facts of the pinned SDK (xmemory.cpp map_info/heaps).
inline constexpr uint64_t kGuestSpan = 0x120000000ull;  // All views, contiguous.
inline constexpr uint64_t kPhysicalOffset = 0x100000000ull;
inline constexpr uint64_t kPreferredBase = 0x100000000ull;  // First MapViews probe.
inline constexpr uint32_t kGuestAccessViolation = 0xc0000005u;

// Every check increments the counter; a failure prints one line to stderr and
// exits 2 (ordinary code only; never called from signal context).
void require(bool condition, const char* message);
unsigned checks();

// Ordinary-code observer for the traced terminal gate. Default: no output.
class Observer {
 public:
  virtual ~Observer() = default;
  virtual void claimed_repair(uintptr_t) {}
  virtual void retry_fault(uintptr_t) {}
  virtual void consumer_exception(uintptr_t, std::exception_ptr) {}
  virtual void declined(uintptr_t) {}
  virtual void recorded(uintptr_t) {}
  virtual void before_terminal(uintptr_t) {}
};

// Identity of the SDK-created shared-memory object, from public SDK state
// (Memory::file_name) cross-checked against the process's own mappings.
struct ShmIdentity {
  std::string name;          // POSIX shm name, "/xenia_memory_<ticks>".
  uint64_t device = 0, inode = 0;
  uint64_t apparent_size = 0;   // st_size (sparse).
  uint64_t allocated_bytes = 0; // st_blocks * 512 (actual tmpfs pages).
  bool unlinked_early = false;
};

struct ProcessMemory {
  uint64_t vm_size_kib = 0, vm_rss_kib = 0, threads = 0;
};

enum class ShmPolicy {
  kSdkContract,      // Name lives until ~Memory (SDK close+unlink).
  kUnlinkAfterMap,   // Owned name unlinked right after verification (crash-safe).
};

enum class AccessResult { kMemory, kMmio, kRepaired, kDeclined };

struct DeclinedFault {
  uintptr_t host_address = 0;
  uint32_t guest_address = 0;
  bool is_write = false;
};

// Guest-memory scratch owned by one attached thread: a real SystemHeapAlloc
// block in the 4 KiB virtual heap, released on detach.
class GuestScratch {
 public:
  static constexpr uint32_t kSize = 0x400;
  static constexpr uint32_t kAlignment = 0x100;
  static constexpr uint32_t kPointers = 0x70;   // M4 EXCEPTION_POINTERS pair.
  static constexpr uint32_t kRecord = 0x80;     // M4 EXCEPTION_RECORD (80 bytes).
  explicit GuestScratch(rex::memory::Memory& memory);
  ~GuestScratch();
  GuestScratch(const GuestScratch&) = delete;
  GuestScratch& operator=(const GuestScratch&) = delete;
  uint32_t guest() const { return guest_; }
  uint8_t* host() const { return host_; }
  bool live() const { return guest_ != 0; }
  void verify_owned() const;
  // Serialize a declined guest read in the M4 record format (big-endian).
  void record_read_violation(uint32_t guest_pc, uint32_t guest_address);
  uint32_t be32(uint32_t offset) const;
  void release();  // Frees the block and verifies the heap no longer holds it.

 private:
  rex::memory::Memory& memory_;
  uint32_t guest_ = 0;
  uint8_t* host_ = nullptr;
};

class Bootstrap {
 public:
  explicit Bootstrap(ShmPolicy policy, Observer* observer = nullptr);
  ~Bootstrap();
  Bootstrap(const Bootstrap&) = delete;
  Bootstrap& operator=(const Bootstrap&) = delete;

  // Preflight through attach + scratch. Requires all checks. When
  // `ownership_path` is set, an ownership record is written as soon as the SDK
  // shm identity is known (stage "initialized") and again after a complete start
  // (stage "started"), so a later failure still leaves the runner an exact,
  // inode-bound record of the one object it may clean up.
  void start(const char* ownership_path = nullptr, const char* mode = "normal");
  void stop();   // Ordered teardown with residue verification.

  rex::memory::Memory& memory() { return *memory_; }
  rex::runtime::MMIOHandler& mmio();
  GuestScratch& scratch() { return *scratch_; }
  const ShmIdentity& shm() const { return shm_; }
  ProcessMemory before_initialize() const { return before_; }
  ProcessMemory after_initialize() const { return after_; }
  uint8_t* arena_base() const;
  size_t arena_size() const { return static_cast<size_t>(kGuestSpan); }
  bool started() const { return started_; }


  // Checked guest-virtual 32-bit accesses (raw host-order bytes). MMIO ranges
  // are consumed first, before any memory access or fault capture.
  AccessResult checked_load32(uint32_t guest_address, uint32_t& value, DeclinedFault* declined);
  AccessResult checked_store32(uint32_t guest_address, uint32_t value);

  // Deferred ordinary-code dispatch into the real SDK MMIOHandler exception
  // callback (which reaches Memory::AccessViolationCallback). Refuses MMIO
  // ranges (the SDK would decode host instructions there).
  bool dispatch(uintptr_t host_address, bool is_write);

  unsigned admitted_faults() const { return admitted_faults_; }
  unsigned consumed_dispatches() const { return consumed_; }
  unsigned declined_dispatches() const { return declined_; }

  [[noreturn]] void terminal(uintptr_t address);

 private:
  void preflight();
  void identify_shared_memory();
  void write_ownership(const char* stage) const;
  void verify_layout();
  void verify_shared_memory();
  void handoff();
#if LRB_NATIVE
  bool admitted(uintptr_t host, bool is_write, unsigned before) const;
  struct sigaction pre_segv_{}, pre_ill_{}, pre_bus_{};
#endif

  ShmPolicy policy_;
  Observer* observer_;
  std::string ownership_path_, mode_;
  Observer quiet_;
  std::unique_ptr<rex::memory::Memory> memory_;
  std::unique_ptr<GuestScratch> scratch_;
  ShmIdentity shm_;
  ProcessMemory before_, after_;
  bool started_ = false, owner_installed_ = false, attached_ = false;
#if LRB_NATIVE
  std::vector<long> baseline_tasks_;  // Captured in the constructor, before any SDK call.
  long main_tid_ = 0;
#endif
  void check_threads(const char* checkpoint) const;
  unsigned admitted_faults_ = 0, consumed_ = 0, declined_ = 0;
};

// Access to protected SDK members through member pointers named in derived
// scope (fully standard; no object slicing or reinterpretation).
struct SdkAccess final : rex::runtime::MMIOHandler {
  using Callback = bool (rex::runtime::MMIOHandler::*)(rex::arch::Exception*);
  static Callback exception_callback() { return &SdkAccess::ExceptionCallback; }
  static rex::arch::ExceptionHandler::Handler exception_thunk() {
    return &SdkAccess::ExceptionCallbackThunk;
  }
};
struct HeapAccess final : rex::memory::PhysicalHeap {
  using Watched = bool (rex::memory::PhysicalHeap::*)(uint32_t) const;
  static Watched watched() { return &HeapAccess::IsHostPageWriteWatched; }
};
bool host_page_watched(rex::memory::BaseHeap* heap, uint32_t guest_address);

rex::memory::PageAccess host_access(const void* host);
ProcessMemory process_memory();

// Thread-set policy (pure; tested on every platform). The pinned SDK defines a
// namespace-scope rex::thread::TimerQueue (src/core/timer_queue.cpp) whose
// constructor starts one std::jthread dispatcher when librexruntime is loaded,
// before main. That thread never attaches to the LRB owner, never calls
// sigaction and never touches guest memory in this bootstrap. The participating
// thread is still exactly one (main). Policy: the task set captured before any
// SDK call must be {main} plus exactly kSdkPreMainThreads others, and it must be
// identical at every later checkpoint (the bootstrap creates no thread).
inline constexpr size_t kSdkPreMainThreads = 1;
// Returns nullptr when acceptable, else a failure message.
const char* thread_set_violation(const std::vector<long>& baseline, const std::vector<long>& now,
                                 long main_tid, size_t expected_pre_main);
std::vector<long> process_tasks();  // Sorted /proc/self/task ids (empty off Linux).

}  // namespace lrb
