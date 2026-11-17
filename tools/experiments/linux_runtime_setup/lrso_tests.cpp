// Linux Runtime Setup Ownership (LRSO) acceptance executable.
//
// Runs the REAL pinned rex::Runtime::Setup (tool mode, no title, no game data,
// no input/audio/graphics factory, no kernel_init) in an isolated subprocess and
// records every signal disposition before and after each ownership transition.
// No generated code is linked. The SDK itself writes guest memory during Setup
// (Memory::Initialize constants, KernelState globals) and the fixture fills its
// own fresh region in ordinary code; the only FAULTING store is the synthetic
// LWR leaf (lwr_test_leaf.S), authorized as an explicitly synthetic code range,
// exactly as the audited LWR probe does.
//
// Two variants, never mixed in one process:
//   default*  Unchanged SDK initialization. rex::initialize_seh() installs the
//             SDK SEH handler, Memory::Initialize installs the MMIO thunk above
//             it. Nothing faults while that handler is live; no competing owner
//             is installed (the LRB owner's own SIG_DFL precondition refuses).
//   latch*    Experimental D1(a): before Setup, the SDK's OWN definition of the
//             public inline rex::platform::g_seh_initialized (found by dlsym; the
//             executable never defines a copy) is set to true, so
//             seh_initialize() returns early. The MMIO thunk then sits above
//             SIG_DFL, the unchanged LRB handoff applies, and one LWR restart
//             runs on a watched page of the runtime-owned memory.
//
// Contracts are re-derived by lrso_gate.py from the records this writes.
#include "lrb_bootstrap.h"

#if !LRB_NATIVE
#error "LRSO is a native Linux x86-64 experiment only"
#endif

#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <string_view>
#include <vector>

#include <dlfcn.h>
#include <pthread.h>
#include <signal.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>

#include <rex/exception_handler.h>
#include <rex/logging/api.h>
#include <rex/logging/types.h>
#include <rex/memory/utils.h>
#include <rex/runtime.h>
#include <rex/system/kernel_state.h>
#include <rex/system/mmio_handler.h>
#include <rex/system/xmemory.h>
#include <rex/thread/mutex.h>

#include "lrb_owner.h"
#include "lwr_restart.h"

extern "C" {
void lwr_leaf_store32(void* p_minus_4, uint32_t v);
extern const unsigned char lwr_leaf_store32_end[];
}

namespace {
using lrb::require;
using rex::memory::Memory;
using rex::memory::PageAccess;
using rex::X_STATUS;  // X_STATUS_SUCCESS expands to an unqualified cast.

// ------------------------------------------------------------------ constants
constexpr uint64_t kGuestSpan = lrb::kGuestSpan;
constexpr uint64_t kBase = lrb::kPreferredBase;
constexpr uint32_t kPage = 0x1000u;
constexpr uint32_t kAliasVa = 0xA4000000u;        // Same real vA allocation as LWR.
constexpr uint32_t kAliasPhysical = 0x04000000u;
constexpr uint32_t kAliasSize = 0x10000u;
constexpr uint32_t kPages = kAliasSize / kPage;
constexpr uint32_t kWatchedPage = 4;              // P4: watched; P3/P5 neighbours stay plain.
constexpr uint32_t kTargetOffset = kWatchedPage * kPage + 0x100u;
constexpr uint32_t kStoreValue = 0x5A17C3E1u;
constexpr unsigned kCycles = 3;                   // latch-cycles only.
constexpr unsigned long kLibcSaRestorer = 0x04000000ul;
// Mangled name of the public inline `rex::platform::g_seh_initialized`
// (include/rex/platform/seh.h). Looked up, never defined, by this executable.
constexpr const char* kLatchSymbol = "_ZN3rex8platform17g_seh_initializedE";

constexpr std::array<std::string_view, 4> kFatal = {"latch-unregistered", "latch-unauthorized",
                                                     "latch-consumed", "latch-foreign-session"};
constexpr std::array<std::string_view, 4> kPositive = {"default", "default-originals", "latch",
                                                        "latch-cycles"};

std::string g_mode;
std::FILE* g_records = nullptr;

void record(const std::string& line) {
  if (!g_records) return;
  require(std::fprintf(g_records, "%s\n", line.c_str()) > 0 && std::fflush(g_records) == 0,
          "write an LRSO record");
}

std::string hex(uint64_t v) {
  char buf[24];
  std::snprintf(buf, sizeof(buf), "0x%" PRIx64, v);
  return buf;
}

// ------------------------------------------------------------------ signal snapshots
struct Action {
  bool valid = false;
  uintptr_t handler = 0;
  bool siginfo = false;
  unsigned long flags = 0;  // SA_RESTORER removed (glibc-private).
  uint64_t mask = 0;        // Bit n-1 for signal n.
};
using Snapshot = std::array<Action, 65>;  // Index = signal number 1..64.

bool skipped(int sig) { return sig == SIGKILL || sig == SIGSTOP; }

Snapshot snapshot() {
  static_assert(NSIG == 65, "glibc x86-64 signal numbering");
  Snapshot s{};
  for (int sig = 1; sig < NSIG; ++sig) {
    if (skipped(sig)) continue;
    struct sigaction a{};
    Action& out = s[sig];
    if (sigaction(sig, nullptr, &a) != 0) {
      require(errno == EINVAL, "signal query fails only for glibc-reserved signals");
      continue;
    }
    out.valid = true;
    out.siginfo = (a.sa_flags & SA_SIGINFO) != 0;
    out.handler = out.siginfo ? reinterpret_cast<uintptr_t>(a.sa_sigaction)
                              : reinterpret_cast<uintptr_t>(a.sa_handler);
    out.flags = static_cast<unsigned long>(a.sa_flags) & ~kLibcSaRestorer;
    for (int m = 1; m < NSIG; ++m)
      if (!skipped(m) && sigismember(&a.sa_mask, m) == 1) out.mask |= 1ull << (m - 1);
  }
  return s;
}

bool same(const Action& a, const Action& b) {
  return a.valid == b.valid && a.handler == b.handler && a.siginfo == b.siginfo && a.flags == b.flags &&
         a.mask == b.mask;
}

std::vector<int> changed(const Snapshot& a, const Snapshot& b) {
  std::vector<int> out;
  for (int sig = 1; sig < NSIG; ++sig)
    if (!skipped(sig) && !same(a[sig], b[sig])) out.push_back(sig);
  return out;
}

bool is_default(const Action& a) { return a.valid && !a.siginfo && a.handler == reinterpret_cast<uintptr_t>(SIG_DFL); }

struct Where {
  std::string object = "-";
  uintptr_t offset = 0;
};

Where where(uintptr_t handler) {
  Where w;
  if (handler == reinterpret_cast<uintptr_t>(SIG_DFL) || handler == reinterpret_cast<uintptr_t>(SIG_IGN)) return w;
  Dl_info info{};
  if (dladdr(reinterpret_cast<void*>(handler), &info) && info.dli_fname) {
    std::string name = info.dli_fname;
    const size_t slash = name.rfind('/');
    w.object = slash == std::string::npos ? name : name.substr(slash + 1);
    if (w.object.empty()) w.object = "main";
    w.offset = handler - reinterpret_cast<uintptr_t>(info.dli_fbase);
  } else {
    w.object = "?";
  }
  return w;
}

bool in_sdk_runtime(uintptr_t handler) { return where(handler).object.rfind("librexruntime.so", 0) == 0; }

void record_snapshot(unsigned cycle, const char* stage, const Snapshot& s) {
  for (int sig = 1; sig < NSIG; ++sig) {
    if (skipped(sig)) continue;
    const Action& a = s[sig];
    const char* state = !a.valid ? "invalid"
                        : (!a.siginfo && a.handler == reinterpret_cast<uintptr_t>(SIG_DFL)) ? "dfl"
                        : (!a.siginfo && a.handler == reinterpret_cast<uintptr_t>(SIG_IGN)) ? "ign"
                                                                                           : "fn";
    const Where w = (a.valid && std::strcmp(state, "fn") == 0) ? where(a.handler) : Where{};
    char buf[96];
    std::snprintf(buf, sizeof(buf), "0x%016" PRIx64, a.mask);
    record("LRSO_SIG_V1|mode=" + g_mode + "|cycle=" + std::to_string(cycle) + "|stage=" + stage +
           "|sig=" + std::to_string(sig) + "|state=" + state + "|siginfo=" + (a.siginfo ? "1" : "0") +
           "|flags=" + hex(a.flags) + "|mask=" + buf + "|object=" + w.object + "|offset=" + hex(w.offset));
  }
}

// ------------------------------------------------------------------ threads
std::vector<long> g_baseline;
long g_main = 0;

void check_threads(unsigned cycle, const char* stage) {
  const std::vector<long> now = lrb::process_tasks();
  const char* violation = lrb::thread_set_violation(g_baseline, now, g_main, lrb::kSdkPreMainThreads);
  record("LRSO_THREADS_V1|mode=" + g_mode + "|cycle=" + std::to_string(cycle) + "|stage=" + stage +
         "|count=" + std::to_string(now.size()) + "|baseline=" + std::to_string(g_baseline.size()) +
         "|equal=" + (violation ? "0" : "1"));
  if (violation) require(false, (std::string(violation) + " at " + stage).c_str());
  require(static_cast<long>(gettid()) == g_main, "LRSO runs on the main thread");
}

// ------------------------------------------------------------------ the SDK latch
std::atomic<bool>* g_latch = nullptr;

// The SDK's own definition, through the global lookup scope (the same scope
// the SDK's GOT reference to it resolves in). The executable has no copy.
void locate_latch() {
  static_assert(std::atomic<bool>::is_always_lock_free && sizeof(std::atomic<bool>) == 1,
                "lock-free one-byte latch");
  void* symbol = dlsym(RTLD_DEFAULT, kLatchSymbol);
  require(symbol != nullptr, "SDK latch symbol resolvable in the global scope");
  Dl_info info{};
  require(dladdr(symbol, &info) && info.dli_fname &&
              std::string_view(info.dli_fname).find("librexruntime.so") != std::string_view::npos,
          "the resolved latch is the SDK library's own definition");
  g_latch = static_cast<std::atomic<bool>*>(symbol);
}

void record_latch(const char* stage) {
  record("LRSO_LATCH_V1|mode=" + g_mode + "|stage=" + stage + "|value=" + (g_latch->load() ? "1" : "0") +
         "|object=" + where(reinterpret_cast<uintptr_t>(g_latch)).object);
}

// ------------------------------------------------------------------ maps / shm
struct MapEntry {
  uint64_t start = 0, end = 0, inode = 0;
  unsigned major = 0, minor = 0;
  char perms[5] = {};
};

std::vector<MapEntry> read_maps() {
  std::vector<MapEntry> entries;
  std::ifstream maps("/proc/self/maps");
  require(maps.is_open(), "open /proc/self/maps");
  std::string line;
  while (std::getline(maps, line)) {
    MapEntry e;
    unsigned long long start = 0, end = 0, offset = 0, inode = 0;
    if (std::sscanf(line.c_str(), "%llx-%llx %4s %llx %x:%x %llu", &start, &end, e.perms, &offset, &e.major,
                    &e.minor, &inode) < 7)
      continue;
    e.start = start;
    e.end = end;
    e.inode = inode;
    entries.push_back(e);
  }
  require(!entries.empty(), "parse /proc/self/maps");
  return entries;
}

bool range_unmapped(uint64_t begin, uint64_t end) {
  for (const auto& e : read_maps())
    if (e.start < end && e.end > begin) return false;
  return true;
}

struct Shm {
  std::string name;
  uint64_t device = 0, inode = 0, apparent = 0, allocated = 0;
  bool unlinked_early = false;
};

Shm identify(Memory& m) {
  Shm shm;
  const std::string name = m.file_name().string();
  require(!name.empty() && name.find('/') == std::string::npos && name.rfind("xenia_memory_", 0) == 0 &&
              name.size() > 13 && name.find_first_not_of("0123456789", 13) == std::string::npos,
          "runtime shm name is xenia_memory_<ticks>");
  shm.name = "/" + name;
  struct stat st{};
  require(stat(("/dev/shm" + shm.name).c_str(), &st) == 0 && S_ISREG(st.st_mode), "runtime shm object exists");
  require(st.st_uid == geteuid(), "runtime shm object owned by this user");
  shm.device = st.st_dev;
  shm.inode = st.st_ino;
  shm.apparent = uint64_t(st.st_size);
  shm.allocated = uint64_t(st.st_blocks) * 512u;
  return shm;
}

// Every mapping in the guest span is a shared mapping of this exact inode and
// the span has no gap: the runtime's views are backed by the identified object.
void verify_views(const Shm& shm) {
  uint64_t cursor = kBase;
  const uint64_t end = kBase + kGuestSpan;
  for (const auto& e : read_maps()) {
    if (e.end <= cursor || e.start >= end) continue;
    require(e.start <= cursor, "runtime views have no gap");
    require(e.perms[3] == 's' && e.inode == shm.inode && e.major == major(shm.device) &&
                e.minor == minor(shm.device),
            "runtime view is a shared mapping of the identified shm inode");
    cursor = e.end < end ? e.end : end;
  }
  require(cursor == end, "runtime views cover the whole guest span");
  require(shm.apparent == 0x120001000ull && shm.allocated < (64ull << 20), "sparse runtime shm size");
}

void unlink_owned(Shm& shm) {
  const std::string path = "/dev/shm" + shm.name;
  struct stat st{};
  require(stat(path.c_str(), &st) == 0 && st.st_ino == shm.inode && st.st_dev == shm.device,
          "owned shm identity unchanged before early unlink");
  require(unlink(path.c_str()) == 0, "early unlink of the owned shm name");
  errno = 0;
  require(stat(path.c_str(), &st) != 0 && errno == ENOENT, "owned shm name gone");
  shm.unlinked_early = true;
}

void write_ownership(const Shm& shm, const char* stage, bool fatal, const lrb::ProcessMemory& before,
                     const lrb::ProcessMemory& after) {
  const char* path = std::getenv("LRB_OWNERSHIP_FILE");
  if (!path || !*path) return;
  const std::string temporary = std::string(path) + ".tmp";
  std::FILE* file = std::fopen(temporary.c_str(), "w");
  require(file != nullptr, "open ownership record");
  std::fprintf(file,
               "{\"format\":\"LRB_OWNERSHIP_V1\",\"stage\":\"%s\",\"mode\":\"%s\",\"policy\":\"%s\",\"pid\":%lld,"
               "\"shm_name\":\"%s\",\"device\":%" PRIu64 ",\"inode\":%" PRIu64 ",\"apparent_size\":%" PRIu64
               ",\"allocated_bytes\":%" PRIu64 ",\"unlinked_early\":%s,\"virtual_membase\":%" PRIu64
               ",\"vm_size_kib_before\":%" PRIu64 ",\"vm_size_kib_after\":%" PRIu64
               ",\"vm_rss_kib_before\":%" PRIu64 ",\"vm_rss_kib_after\":%" PRIu64 "}\n",
               stage, g_mode.c_str(), fatal ? "unlink-after-map" : "sdk-contract", static_cast<long long>(getpid()),
               shm.name.c_str(), shm.device, shm.inode, shm.apparent, shm.allocated,
               shm.unlinked_early ? "true" : "false", kBase, before.vm_size_kib, after.vm_size_kib,
               before.vm_rss_kib, after.vm_rss_kib);
  require(std::fflush(file) == 0 && std::fclose(file) == 0, "write ownership record");
  require(std::rename(temporary.c_str(), path) == 0, "publish ownership record atomically");
}

// ------------------------------------------------------------------ witness (traced modes)
struct Witness {
  char token[33] = {};
  bool valid = false;
  explicit Witness(const char* t) {
    valid = t && std::strlen(t) == 32;
    for (unsigned i = 0; valid && i < 32; ++i) valid = (t[i] >= '0' && t[i] <= '9') || (t[i] >= 'a' && t[i] <= 'f');
    if (valid) std::memcpy(token, t, 33);
  }
};
Witness* g_witness = nullptr;
unsigned g_invalidations = 0;

void emit(const char* phase, uintptr_t address) {
  if (!g_witness) return;
  std::array<char, 256> line{};
  const int n = std::snprintf(line.data(), line.size(),
                              "LRSO_GATE_V1 token=%s mode=%s phase=%s claims=%u invalidations=%u address=0x%llx\n",
                              g_witness->token, g_mode.c_str(), phase, lwr_claim_count(), g_invalidations,
                              static_cast<unsigned long long>(address));
  if (n > 0 && static_cast<size_t>(n) < line.size()) {
    (void)std::fwrite(line.data(), 1, static_cast<size_t>(n), stderr);
    (void)std::fflush(stderr);
  }
}

// ------------------------------------------------------------------ runtime lifecycle
struct Cycle {
  unsigned index = 0;
  bool latch = false, fatal = false;
  rex::Runtime* runtime = nullptr;
  Memory* memory = nullptr;
  rex::runtime::MMIOHandler* mmio = nullptr;
  Shm shm;
};

void preflight(const Snapshot& entry) {
  for (int sig : {SIGSEGV, SIGILL, SIGBUS, SIGFPE})
    require(is_default(entry[sig]), "SIGSEGV/SIGILL/SIGBUS/SIGFPE unowned before Runtime::Setup");
  stack_t stack{};
  require(sigaltstack(nullptr, &stack) == 0 && (stack.ss_flags & SS_DISABLE), "no alternate signal stack");
  require(range_unmapped(kBase, kBase + kGuestSpan), "guest view range unmapped before Runtime::Setup");
  require(rex::memory::page_size() == kPage, "4 KiB host pages (tested configuration)");
  require(rex::runtime::MMIOHandler::global_handler() == nullptr, "no SDK MMIOHandler before Setup");
  require(rex::Runtime::instance() == nullptr && rex::system::KernelState::shared() == nullptr,
          "no runtime or kernel singleton before Setup");
}

// The real Runtime::Setup in tool mode: empty roots (VFS skipped), no factories.
void setup(Cycle& c, const Snapshot& entry) {
  preflight(entry);
  const auto before = lrb::process_memory();
  rex::RuntimeConfig config;
  config.tool_mode = true;
  const X_STATUS status = c.runtime->Setup(std::move(config));
  require(status == X_STATUS_SUCCESS, "real Runtime::Setup (tool mode) succeeded");
  const auto after = lrb::process_memory();
  check_threads(c.index, "after-setup");
  c.memory = c.runtime->memory();
  c.mmio = rex::runtime::MMIOHandler::global_handler();
  require(c.memory != nullptr && c.mmio != nullptr, "runtime owns Memory and the SDK MMIOHandler");
  require(rex::Runtime::instance() == c.runtime && c.runtime->is_tool_mode(), "runtime singleton in tool mode");
  require(rex::system::KernelState::shared() == c.runtime->kernel_state() && c.runtime->kernel_state() != nullptr,
          "kernel state singleton owned by the runtime");
  require(c.runtime->function_dispatcher() != nullptr && c.runtime->export_resolver() != nullptr &&
              c.runtime->file_system() != nullptr,
          "dispatcher, export resolver and VFS created");
  require(c.runtime->graphics_system() == nullptr && c.runtime->audio_system() == nullptr &&
              c.runtime->input_system() == nullptr,
          "no graphics, audio or input system");
  require(reinterpret_cast<uintptr_t>(c.memory->virtual_membase()) == kBase &&
              c.memory->physical_membase() == c.memory->virtual_membase() + lrb::kPhysicalOffset,
          "runtime views at 2^32, physical at +4 GiB");
  c.shm = identify(*c.memory);
  write_ownership(c.shm, "initialized", c.fatal, before, after);
  verify_views(c.shm);
  if (c.fatal) unlink_owned(c.shm);  // Crash-safe: the name cannot outlive a fatal child.
  write_ownership(c.shm, "started", c.fatal, before, after);
  record("LRSO_RUNTIME_V1|mode=" + g_mode + "|cycle=" + std::to_string(c.index) + "|setup_status=" + hex(status) +
         "|instance=1|kernel_shared=1|mmio=1|membase=" + hex(kBase) + "|tool_mode=1|shm=" + c.shm.name +
         "|inode=" + std::to_string(c.shm.inode) + "|device=" + std::to_string(c.shm.device));
}

// Ownership after Setup, compared against the entry snapshot. Returns the SDK
// SEH action (default variant) for later comparisons.
Action check_after_setup(const Cycle& c, const Snapshot& entry, const Snapshot& now) {
  const Action& segv = now[SIGSEGV];
  const Action& ill = now[SIGILL];
  require(segv.valid && segv.siginfo && in_sdk_runtime(segv.handler) && segv.flags == static_cast<unsigned long>(SA_SIGINFO) && segv.mask == 0,
          "SIGSEGV is the SDK MMIO thunk (SA_SIGINFO, empty mask)");
  require(same(segv, ill), "SIGILL is the same SDK MMIO thunk");
  std::vector<int> expect = {SIGILL, SIGSEGV};  // Ascending, as changed() returns.
  Action seh{};
  if (c.latch) {
    require(is_default(now[SIGBUS]) && is_default(now[SIGFPE]),
            "latch: SIGBUS/SIGFPE untouched (seh_initialize returned early)");
  } else {
    seh = now[SIGFPE];
    require(seh.valid && seh.siginfo && in_sdk_runtime(seh.handler) &&
                seh.flags == static_cast<unsigned long>(SA_SIGINFO | SA_NODEFER) && seh.mask == 0,
            "default: SIGFPE is the SDK SEH handler (SA_SIGINFO|SA_NODEFER, empty mask)");
    require(same(now[SIGBUS], seh), "default: SIGBUS is the same SDK SEH handler");
    require(seh.handler != segv.handler, "default: SEH handler and MMIO thunk are distinct functions");
    expect = {SIGILL, SIGBUS, SIGFPE, SIGSEGV};
  }
  std::sort(expect.begin(), expect.end());
  require(changed(entry, now) == expect, "Setup changed exactly the expected signal dispositions");
  return seh;
}

void teardown(Cycle& c, const Snapshot& expect_final) {
  const uint8_t* former = c.memory->virtual_membase();
  c.runtime->Shutdown();
  require(rex::Runtime::instance() == nullptr && rex::system::KernelState::shared() == nullptr &&
              c.runtime->memory() == nullptr,
          "Shutdown releases the runtime, kernel state and Memory");
  require(rex::runtime::MMIOHandler::global_handler() == nullptr, "SDK MMIOHandler removed with Memory");
  require(reinterpret_cast<uintptr_t>(former) == kBase && range_unmapped(kBase, kBase + kGuestSpan),
          "no runtime view remains mapped after Shutdown");
  stack_t stack{};
  require(sigaltstack(nullptr, &stack) == 0 && (stack.ss_flags & SS_DISABLE), "alternate stack removed");
  struct stat st{};
  errno = 0;
  require(stat(("/dev/shm" + c.shm.name).c_str(), &st) != 0 && errno == ENOENT,
          "no runtime /dev/shm residue after Shutdown");
  const Snapshot now = snapshot();
  record_snapshot(c.index, "after-shutdown", now);
  require(changed(expect_final, now).empty(), "dispositions after Shutdown are exactly the expected ones");
  check_threads(c.index, "after-shutdown");
  record("LRSO_TEARDOWN_V1|mode=" + g_mode + "|cycle=" + std::to_string(c.index) +
         "|instance=0|kernel_shared=0|mmio=0|views_unmapped=1|shm_removed=1|altstack_disabled=1");
}

// ------------------------------------------------------------------ LRB handoff (latch only)
void handoff(Cycle& c, const Snapshot& entry) {
  // Exactly the LRB handoff: remove only the thunk MMIOHandler::Install
  // registered; the MMIOHandler object and Memory's callbacks stay live.
  rex::arch::ExceptionHandler::Uninstall(lrb::SdkAccess::exception_thunk(), c.mmio);
  require(rex::runtime::MMIOHandler::global_handler() == c.mmio, "MMIOHandler singleton survives the handoff");
  Snapshot now = snapshot();
  record_snapshot(c.index, "after-thunk-removal", now);
  require(changed(entry, now).empty(), "thunk removal restores SIG_DFL beneath (every disposition as at entry)");
  require(lrb_install() == 0, "install the exclusive LRB SIGSEGV owner");
  require(lrb_owns_sigsegv() == 1, "LRB owner is the only live SIGSEGV action");
  now = snapshot();
  record_snapshot(c.index, "after-owner", now);
  require(changed(entry, now) == std::vector<int>{SIGSEGV}, "the owner changed SIGSEGV only");
  require(lrb_attach() == 0, "attach guarded alternate signal stack");
  check_threads(c.index, "after-owner");
  record("LRSO_HANDOFF_V1|mode=" + g_mode + "|cycle=" + std::to_string(c.index) +
         "|result=installed|segv_beneath=sig_dfl");
}

void release_owner(Cycle& c, const Snapshot& entry) {
  require(lrb_detach() == 0, "detach after the restart");
  require(lrb_uninstall() == 0 && lrb_installed() == 0, "remove the LRB owner before Shutdown");
  const Snapshot now = snapshot();
  record_snapshot(c.index, "after-owner-removal", now);
  require(changed(entry, now).empty(), "owner removal restores every entry disposition");
}

// ------------------------------------------------------------------ the LWR restart
struct Region {
  Memory* memory = nullptr;
  rex::memory::BaseHeap* heap = nullptr;
  uint8_t* alias = nullptr;
  void* callback = nullptr;
  uint32_t per_page[kPages] = {};
  bool bad = false;
};

std::pair<uint32_t, uint32_t> invalidated(void* opaque, uint32_t physical, uint32_t length, bool /*exact*/) {
  auto& r = *static_cast<Region*>(opaque);
  ++g_invalidations;
  if (physical < kAliasPhysical || length != kPage || (physical & (kPage - 1)) ||
      physical - kAliasPhysical >= kAliasSize)
    r.bad = true;
  else
    ++r.per_page[(physical - kAliasPhysical) / kPage];
  return {physical, length};
}

uint8_t* page(Region& r, uint32_t n) { return r.alias + n * kPage; }
bool watched(Region& r, uint32_t n) { return lrb::host_page_watched(r.heap, kAliasVa + n * kPage); }

void verify_plain(Region& r, const char* what) {
  for (uint32_t n = 0; n < kPages; ++n)
    require(lrb::host_access(page(r, n)) == PageAccess::kReadWrite && !watched(r, n), what);
}

void allocate(Region& r, Memory& m) {
  r.memory = &m;
  r.heap = m.LookupHeap(kAliasVa);
  require(r.heap && r.heap->heap_type() == rex::memory::HeapType::kGuestPhysical,
          "region heap is the runtime's vA physical alias heap");
  require(r.heap->AllocFixed(kAliasVa, kAliasSize, kAliasSize,
                             rex::memory::kMemoryAllocationReserve | rex::memory::kMemoryAllocationCommit,
                             rex::memory::kMemoryProtectRead | rex::memory::kMemoryProtectWrite),
          "real fixed vA physical allocation in runtime-owned Memory");
  require(m.GetPhysicalAddress(kAliasVa) == kAliasPhysical, "region physical address");
  r.alias = m.TranslateVirtual(kAliasVa);
  require(r.alias == m.virtual_membase() + kAliasVa, "region translation is base + guest");
  verify_plain(r, "region pages plain after allocation");
  r.callback = m.RegisterPhysicalMemoryInvalidationCallback(invalidated, &r);
  require(r.callback != nullptr, "register the invalidation callback");
}

void release(Region& r) {
  r.memory->UnregisterPhysicalMemoryInvalidationCallback(r.callback);
  uint32_t released = 0;
  require(r.heap->Release(kAliasVa, &released) && released == kAliasSize, "region released exactly");
}

void fill(Region& r) {
  for (uint32_t i = 0; i < kAliasSize; ++i) r.alias[i] = static_cast<uint8_t>((i * 131u + 7u) ^ (i >> 8));
}

void watch(Region& r) {
  r.memory->EnablePhysicalMemoryAccessCallbacks(kAliasPhysical + kWatchedPage * kPage, kPage, true, false);
  require(lrb::host_access(page(r, kWatchedPage)) == PageAccess::kReadOnly && watched(r, kWatchedPage),
          "real SDK watch: runtime alias page read-only and watched");
}

bool trigger(Region& r) {
  return r.memory->TriggerPhysicalMemoryCallbacks(rex::thread::global_critical_region::AcquireDirect(),
                                                  kAliasVa + kWatchedPage * kPage, 1, true, false, true);
}

void authorize_leaf() {
  const lwr_range leaf{reinterpret_cast<uintptr_t>(&lwr_leaf_store32),
                       reinterpret_cast<uintptr_t>(lwr_leaf_store32_end)};
  require(lwr_authorize(&leaf, 1) == 0, "authorize the explicitly synthetic leaf");
}

uint8_t* target(Region& r) { return r.alias + kTargetOffset; }

// One ordinary store (no watch) gives the reference bytes; then the same store
// on the watched page faults, is admitted once, restarts without any context
// edit and is drained once through the real SDK invalidation path.
void restart(Cycle& c, Region& r) {
  fill(r);
  lwr_leaf_store32(target(r) - 4, kStoreValue);  // Ordinary: page writable, no fault.
  const std::vector<uint8_t> expected(r.alias, r.alias + kAliasSize);
  uint32_t stored = 0;
  std::memcpy(&stored, target(r), 4);
  require(stored == kStoreValue, "ordinary leaf store committed");
  fill(r);
  const std::vector<uint8_t> before(r.alias, r.alias + kAliasSize);
  verify_plain(r, "region plain before the watched store");
  g_invalidations = 0;
  watch(r);
  require(lwr_open() == 0, "open the LWR session");
  require(lwr_register_page(page(r, kWatchedPage)) == 0, "register the watched runtime page");
  authorize_leaf();
  const uintptr_t address = reinterpret_cast<uintptr_t>(target(r));
  lwr_leaf_store32(target(r) - 4, kStoreValue);  // Faults, admitted, restarts.
  require(lwr_revoke() == 0, "revoke after the store");
  emit("claim", address);
  require(lwr_claim_count() == 1, "exactly one claim");
  lwr_claim claim{};
  require(lwr_get_claim(0, &claim) == 0, "read the claim");
  require(claim.page == reinterpret_cast<uintptr_t>(page(r, kWatchedPage)) && claim.address == address &&
              claim.effective == address && claim.width == 4 && claim.length == 3 && claim.error == 7ul &&
              claim.instruction == reinterpret_cast<uintptr_t>(&lwr_leaf_store32),
          "claim: exact page, kernel address, decoded store, saved RIP and write error code");
  require(std::memcmp(claim.before, before.data() + kTargetOffset, 4) == 0, "store had not committed at the fault");
  require(lwr_page_state(page(r, kWatchedPage)) == LWR_PAGE_CLAIMED, "page claimed");
  require(watched(r, kWatchedPage) && lrb::host_access(page(r, kWatchedPage)) == PageAccess::kReadWrite,
          "restart: page writable, SDK watch bit still set (no SDK state touched in signal context)");
  require(g_invalidations == 0, "no invalidation before the ordinary-code drain");
  require(trigger(r), "drain: real SDK invalidation for the claimed page");
  require(!r.bad && g_invalidations == 1 && r.per_page[kWatchedPage] == 1, "exactly one invalidation, for P4");
  require(!watched(r, kWatchedPage), "drain unwatches exactly the claimed page");
  require(lwr_close() == 0 && lwr_claim_count() == 0, "close the LWR session");
  const bool equal = std::memcmp(r.alias, expected.data(), kAliasSize) == 0;
  require(equal, "watched region bytes equal the ordinary store exactly (one store, nothing else written)");
  verify_plain(r, "region plain after the restart");
  require(lrb_owns_sigsegv() == 1, "LRB owner still exclusive after the restart");
  record("LRSO_RESTART_V1|mode=" + g_mode + "|cycle=" + std::to_string(c.index) + "|page=4|target_offset=" +
         hex(kTargetOffset) + "|width=4|length=3|error=7|claims=1|invalidations=1|region_equal=1|watch_cleared=1");
  r.per_page[kWatchedPage] = 0;
}

// ------------------------------------------------------------------ fatal modes (latch, traced)
struct Foreign {
  Region* region;
  pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
  pthread_cond_t cond = PTHREAD_COND_INITIALIZER;
  bool ready = false;
};

void* foreign_session(void* raw) {
  auto* f = static_cast<Foreign*>(raw);
  require(lwr_open() == 0 && lwr_register_page(page(*f->region, kWatchedPage)) == 0,
          "foreign thread session and page");
  authorize_leaf();
  pthread_mutex_lock(&f->lock);
  f->ready = true;
  pthread_cond_signal(&f->cond);
  pthread_mutex_unlock(&f->lock);
  for (;;) pause();
  return nullptr;
}

// Each mode prepares one unsupported fault on the runtime-owned watched page;
// nothing admits it, so the LRB owner must terminate in signal context.
[[noreturn]] void run_fatal(Region& r, std::string_view mode) {
  fill(r);
  const uintptr_t address = reinterpret_cast<uintptr_t>(target(r));
  watch(r);
  if (mode == "latch-foreign-session") {
    static Foreign f;
    f.region = &r;
    pthread_t t;
    require(pthread_create(&t, nullptr, foreign_session, &f) == 0, "start the foreign session thread");
    pthread_mutex_lock(&f.lock);
    while (!f.ready) pthread_cond_wait(&f.cond, &f.lock);
    pthread_mutex_unlock(&f.lock);
    require(lwr_open() == EBUSY, "the session belongs to the other thread");
    emit("begin", address);
    lwr_leaf_store32(target(r) - 4, kStoreValue);
    require(false, "foreign-session store returned");
  }
  require(lwr_open() == 0, "open the LWR session");
  if (mode == "latch-unregistered") {
    authorize_leaf();
    emit("begin", address);
    lwr_leaf_store32(target(r) - 4, kStoreValue);
    require(false, "unregistered store returned");
  }
  require(lwr_register_page(page(r, kWatchedPage)) == 0, "register P4");
  if (mode == "latch-unauthorized") {
    emit("begin", address);
    lwr_leaf_store32(target(r) - 4, kStoreValue);
    require(false, "unauthorized store returned");
  }
  if (mode == "latch-consumed") {
    authorize_leaf();
    emit("begin", address);
    lwr_leaf_store32(target(r) - 4, kStoreValue);
    require(lwr_revoke() == 0 && lwr_claim_count() == 1 && lwr_page_state(page(r, kWatchedPage)) == LWR_PAGE_CLAIMED,
            "first fault admitted once");
    emit("claimed", address);
    require(trigger(r) && g_invalidations == 1 && !watched(r, kWatchedPage), "drained through the real SDK path");
    watch(r);  // The SDK re-watches the page; the LWR slot stays consumed.
    authorize_leaf();
    emit("rewatched", address);
    lwr_leaf_store32(target(r) - 4, kStoreValue);
    require(false, "consumed-slot store returned");
  }
  require(false, "unknown fatal mode");
  std::abort();
}

bool contains(const auto& list, std::string_view mode) {
  return std::find(list.begin(), list.end(), mode) != list.end();
}
}  // namespace

int main(int argc, char** argv) {
  // Before any SDK call: only the load-time (pre-main) TimerQueue thread exists.
  const Snapshot entry = snapshot();
  g_main = static_cast<long>(getpid());
  require(static_cast<long>(gettid()) == g_main, "started on the main thread");
  g_baseline = lrb::process_tasks();
  require(argc == 2, "exactly one mode");
  g_mode = argv[1];
  const bool fatal = contains(kFatal, g_mode);
  const bool traced_positive = g_mode == "latch-traced-positive";
  require(fatal || traced_positive || contains(kPositive, g_mode), "supported LRSO mode");
  const bool latch = g_mode.rfind("latch", 0) == 0;
  const unsigned cycles = g_mode == "latch-cycles" ? kCycles : 1u;
  const rlimit no_core{0, 0};
  require(setrlimit(RLIMIT_CORE, &no_core) == 0, "disable core dumps");
  Witness witness(std::getenv("LRB_GATE_TOKEN"));
  if (fatal || traced_positive) {
    require(witness.valid, "traced modes require a 32-hex LRB_GATE_TOKEN");
    g_witness = &witness;
  }
  if (const char* path = std::getenv("LRSO_RECORD_FILE"); path && *path) {
    g_records = std::fopen(path, "w");
    require(g_records != nullptr, "open the LRSO record file");
  }
  record_snapshot(0, "entry", entry);
  check_threads(0, "entry");
  locate_latch();
  record_latch("entry");
  require(g_latch->load() == false, "SDK SEH latch clear at entry (seh_initialize never ran)");

  // SDK logging: no console or file sink (as LRB), so output stays exact.
  rex::LogConfig log{};
  log.log_to_console = std::getenv("LRB_SDK_LOG_CONSOLE") != nullptr;
  rex::InitLogging(log);
  const Snapshot logged = snapshot();
  record_snapshot(0, "after-logging", logged);
  require(changed(entry, logged).empty(), "logging initialization changed no signal disposition");
  check_threads(0, "after-logging");

  if (latch) {
    // EXPERIMENTAL D1(a), test executable only: suppress the SDK SEH handler.
    g_latch->store(true);
    record_latch("after-store");
  }

  unsigned claims = 0;
  for (unsigned i = 1; i <= cycles; ++i) {
    rex::Runtime runtime{std::filesystem::path{}};
    Cycle c;
    c.index = i;
    c.latch = latch;
    c.fatal = fatal;
    c.runtime = &runtime;
    setup(c, entry);
    if (i == 1) record_latch("after-setup");
    require(g_latch->load(), "SDK SEH latch set after Setup in both variants");
    const Snapshot after = snapshot();
    record_snapshot(i, "after-setup", after);
    const Action seh = check_after_setup(c, entry, after);
    if (!latch) {
      Snapshot expect_final = entry;
      for (int sig : {SIGSEGV, SIGILL, SIGBUS, SIGFPE}) expect_final[sig] = seh;
      if (g_mode == "default-originals") {
        // Reveal what the MMIO thunk saved as "original": remove only the thunk.
        rex::arch::ExceptionHandler::Uninstall(lrb::SdkAccess::exception_thunk(), c.mmio);
        const Snapshot removed = snapshot();
        record_snapshot(i, "after-thunk-removal", removed);
        require(changed(expect_final, removed).empty(),
                "default: the thunk's saved originals are the SDK SEH handler, not SIG_DFL");
        // The LRB owner's own precondition refuses to compete with it.
        require(lrb_install() == EBUSY && lrb_installed() == 0, "LRB owner refuses: SIGSEGV is not SIG_DFL");
        const Snapshot refused = snapshot();
        record_snapshot(i, "after-owner-refused", refused);
        require(changed(removed, refused).empty(), "the refused install changed nothing");
        record("LRSO_HANDOFF_V1|mode=" + g_mode + "|cycle=" + std::to_string(i) +
               "|result=refused-ebusy|segv_beneath=sdk-seh");
      } else {
        record("LRSO_HANDOFF_V1|mode=" + g_mode + "|cycle=" + std::to_string(i) +
               "|result=not-attempted|segv_beneath=unobserved");
      }
      check_threads(i, "after-owner");
      teardown(c, expect_final);
      record_latch("after-shutdown");
      continue;
    }
    handoff(c, entry);
    Region region;
    allocate(region, *c.memory);
    require(lrb_owns_sigsegv() == 1, "LRB owner exclusive before the restart");
    if (fatal) run_fatal(region, g_mode);
    restart(c, region);
    ++claims;  // restart() required exactly one claim and one invalidation.
    release(region);
    const Snapshot restarted = snapshot();
    record_snapshot(i, "after-restart", restarted);
    require(changed(entry, restarted) == std::vector<int>{SIGSEGV}, "only the owner is live after the restart");
    check_threads(i, "after-restart");
    release_owner(c, entry);
    teardown(c, entry);
    if (i == cycles) record_latch("after-shutdown");
  }
  if (g_records) require(std::fclose(g_records) == 0, "close the LRSO record file");
  std::printf("LRSO PASS mode=%s variant=%s cycles=%u claims=%u invalidations=%u checks=%u tasks=%zu native=1\n",
              g_mode.c_str(), latch ? "latch" : "default", cycles, claims, latch ? claims : 0u, lrb::checks(),
              g_baseline.size());
  return 0;
}
