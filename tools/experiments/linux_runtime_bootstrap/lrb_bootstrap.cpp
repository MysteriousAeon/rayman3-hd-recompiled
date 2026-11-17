#include "lrb_bootstrap.h"

#include <cerrno>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <algorithm>
#include <string>
#include <vector>

#include <rex/logging/api.h>
#include <rex/logging/types.h>
#include <rex/memory/utils.h>

#if LRB_NATIVE
#include <dirent.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>
#include "lrb_owner.h"
#endif

namespace lrb {
namespace {
using rex::memory::Memory;
using rex::memory::PageAccess;
using Exception = rex::arch::Exception;
using Operation = Exception::AccessViolationOperation;

unsigned g_checks = 0;

#if LRB_NATIVE
// Same order and targets as the pinned xmemory.cpp map_info table.
struct View {
  uint64_t start, end, target;
};
constexpr View kViews[] = {
    {0x00000000ull, 0x3FFFFFFFull, 0x000000000ull}, {0x40000000ull, 0x7EFFFFFFull, 0x040000000ull},
    {0x7F000000ull, 0x7FFFFFFFull, 0x100000000ull}, {0x80000000ull, 0x8FFFFFFFull, 0x080000000ull},
    {0x90000000ull, 0x9FFFFFFFull, 0x080000000ull}, {0xA0000000ull, 0xBFFFFFFFull, 0x100000000ull},
    {0xC0000000ull, 0xDFFFFFFFull, 0x100000000ull}, {0xE0000000ull, 0xFFFFFFFFull, 0x100001000ull},
    {0x100000000ull, 0x11FFFFFFFull, 0x100000000ull},
};

struct MapEntry {
  uint64_t start = 0, end = 0, offset = 0, inode = 0;
  unsigned major = 0, minor = 0;
  char perms[5] = {};
  std::string path;
};

std::vector<MapEntry> read_maps() {
  std::vector<MapEntry> entries;
  std::ifstream maps("/proc/self/maps");
  require(maps.is_open(), "open /proc/self/maps");
  std::string line;
  while (std::getline(maps, line)) {
    MapEntry e;
    unsigned long long start = 0, end = 0, offset = 0, inode = 0;
    int consumed = 0;
    if (std::sscanf(line.c_str(), "%llx-%llx %4s %llx %x:%x %llu %n", &start, &end, e.perms,
                    &offset, &e.major, &e.minor, &inode, &consumed) < 7)
      continue;
    e.start = start;
    e.end = end;
    e.offset = offset;
    e.inode = inode;
    if (consumed > 0 && static_cast<size_t>(consumed) <= line.size()) e.path = line.substr(consumed);
    entries.push_back(std::move(e));
  }
  require(!entries.empty(), "parse /proc/self/maps");
  return entries;
}

bool range_unmapped(const std::vector<MapEntry>& maps, uint64_t begin, uint64_t end) {
  for (const auto& e : maps)
    if (e.start < end && e.end > begin) return false;
  return true;
}

void snapshot_action(int signal_number, struct sigaction& out) {
  require(sigaction(signal_number, nullptr, &out) == 0, "query signal disposition");
}

bool is_default(const struct sigaction& a) {
  return !(a.sa_flags & SA_SIGINFO) && a.sa_handler == SIG_DFL;
}

void verify_restored(int signal_number, const struct sigaction& before, const char* message) {
  struct sigaction after{};
  snapshot_action(signal_number, after);
  require(!(after.sa_flags & SA_SIGINFO) && !(before.sa_flags & SA_SIGINFO) &&
              after.sa_handler == before.sa_handler,
          message);
  // glibc may normalize its private x86-64 SA_RESTORER bit on round trips.
  constexpr unsigned long kLibcSaRestorer = 0x04000000ul;
  require((static_cast<unsigned long>(after.sa_flags) & ~kLibcSaRestorer) ==
              (static_cast<unsigned long>(before.sa_flags) & ~kLibcSaRestorer),
          "restored signal flags exactly (ignoring libc SA_RESTORER)");
  for (int candidate = 1; candidate < NSIG; ++candidate) {
    if (candidate == SIGKILL || candidate == SIGSTOP) continue;
    const int was = sigismember(&before.sa_mask, candidate);
    const int now = sigismember(&after.sa_mask, candidate);
    if (was >= 0 && now >= 0) require(was == now, "restored signal mask exactly");
  }
}
#endif

}  // namespace

void require(bool condition, const char* message) {
  ++g_checks;
  if (condition) return;
  std::fprintf(stderr, "LRB FAIL: %s\n", message);
  std::fflush(stderr);
  std::exit(2);
}

unsigned checks() { return g_checks; }

PageAccess host_access(const void* host) {
  size_t length = rex::memory::page_size();
  PageAccess access = PageAccess::kNoAccess;
  require(rex::memory::QueryProtect(const_cast<void*>(host), length, access) &&
              length >= rex::memory::page_size(),
          "query host page protection");
  return access;
}

ProcessMemory process_memory() {
  ProcessMemory result{};
#if LRB_NATIVE
  std::ifstream status("/proc/self/status");
  std::string line;
  while (std::getline(status, line)) {
    unsigned long long value = 0;
    if (std::sscanf(line.c_str(), "VmSize: %llu kB", &value) == 1) result.vm_size_kib = value;
    if (std::sscanf(line.c_str(), "VmRSS: %llu kB", &value) == 1) result.vm_rss_kib = value;
    if (std::sscanf(line.c_str(), "Threads: %llu", &value) == 1) result.threads = value;
  }
#endif
  return result;
}

bool host_page_watched(rex::memory::BaseHeap* heap, uint32_t guest_address) {
  require(heap && heap->heap_type() == rex::memory::HeapType::kGuestPhysical,
          "watch query targets a physical alias heap");
  auto* physical = static_cast<rex::memory::PhysicalHeap*>(heap);
  const uint32_t page = static_cast<uint32_t>(rex::memory::page_size());
  const uint32_t number = (guest_address - heap->heap_base() + heap->host_address_offset()) / page;
  return (physical->*HeapAccess::watched())(number);
}

// ---------------------------------------------------------------- scratch

GuestScratch::GuestScratch(Memory& memory) : memory_(memory) {
  guest_ = memory_.SystemHeapAlloc(kSize, kAlignment, rex::memory::kSystemHeapVirtual);
  require(guest_ != 0, "owned guest scratch allocated from the real system heap");
  host_ = memory_.TranslateVirtual(guest_);
  verify_owned();
}

GuestScratch::~GuestScratch() {
  if (guest_) release();
}

void GuestScratch::verify_owned() const {
  require(guest_ != 0 && host_ != nullptr, "scratch is live");
  require((guest_ % kAlignment) == 0, "scratch guest alignment");
  require(guest_ < 0x40000000u && uint64_t(guest_) + kSize <= 0x40000000u,
          "scratch lies in the 4 KiB virtual heap");
  const auto* heap = memory_.LookupHeap(guest_);
  require(heap == memory_.LookupHeapByType(false, 4096) &&
              heap->heap_type() == rex::memory::HeapType::kGuestVirtual,
          "scratch heap is the virtual 4 KiB system heap");
  rex::memory::HeapAllocationInfo info{};
  require(const_cast<rex::memory::BaseHeap*>(heap)->QueryRegionInfo(guest_, &info) &&
              (info.state & rex::memory::kMemoryAllocationCommit) &&
              (info.protect & rex::memory::kMemoryProtectWrite) && info.region_size >= kSize,
          "scratch region committed writable for its full size");
  require(host_ == memory_.virtual_membase() + guest_ &&
              memory_.HostToGuestVirtual(host_) == guest_,
          "scratch host/guest translation is exact");
  require(host_ < memory_.physical_membase() &&
              memory_.GetPhysicalAddress(guest_) == UINT32_MAX,
          "scratch is not a physical alias (no host/guest alias confusion)");
  require(host_access(host_) == PageAccess::kReadWrite, "scratch host page writable");
}

uint32_t GuestScratch::be32(uint32_t offset) const {
  require(live() && offset <= kSize - 4, "scratch read inside its reservation");
  const uint8_t* p = host_ + offset;
  return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | p[3];
}

void GuestScratch::record_read_violation(uint32_t guest_pc, uint32_t guest_address) {
  verify_owned();
  require(guest_pc != 0 && (guest_pc & 3u) == 0 && (guest_address & 3u) == 0,
          "bounded record contract: aligned pc and 32-bit read address");
  auto put = [&](uint32_t offset, uint32_t value) {
    require(offset <= kSize - 4, "record write inside scratch");
    uint8_t* p = host_ + offset;
    p[0] = uint8_t(value >> 24); p[1] = uint8_t(value >> 16);
    p[2] = uint8_t(value >> 8);  p[3] = uint8_t(value);
  };
  for (uint32_t offset = kRecord; offset < kRecord + 80; offset += 4) put(offset, 0);
  put(kPointers, guest_ + kRecord);  // ExceptionRecord
  put(kPointers + 4, 0);              // ContextRecord: not supplied (no guest context editing)
  put(kRecord + 0, kGuestAccessViolation);
  put(kRecord + 4, 0);                // flags
  put(kRecord + 8, 0);                // chained record
  put(kRecord + 12, guest_pc);        // exception address
  put(kRecord + 16, 2);               // parameter count
  put(kRecord + 20, 0);               // read
  put(kRecord + 24, guest_address);
}

void GuestScratch::release() {
  require(guest_ != 0, "scratch released once");
  auto* heap = memory_.LookupHeap(guest_);
  uint32_t released = 0;
  memory_.SystemHeapFree(guest_, &released);
  require(released >= kSize, "scratch release reports the owned region size");
  rex::memory::HeapAllocationInfo info{};
  require(heap->QueryRegionInfo(guest_, &info) && info.state == 0,
          "scratch region is free after release");
  guest_ = 0;
  host_ = nullptr;
}

// -------------------------------------------------------------- bootstrap

const char* thread_set_violation(const std::vector<long>& baseline, const std::vector<long>& now,
                                 long main_tid, size_t expected_pre_main) {
  if (std::find(baseline.begin(), baseline.end(), main_tid) == baseline.end())
    return "main thread missing from the pre-SDK task set";
  if (baseline.size() != 1 + expected_pre_main)
    return "unexpected pre-main thread count (expected main + the SDK TimerQueue dispatcher)";
  if (now != baseline) return "task set changed during the bootstrap (a thread was created or exited)";
  return nullptr;
}

std::vector<long> process_tasks() {
  std::vector<long> tasks;
#if LRB_NATIVE
  DIR* dir = opendir("/proc/self/task");
  require(dir != nullptr, "open /proc/self/task");
  while (const dirent* entry = readdir(dir)) {
    char* end = nullptr;
    const long tid = std::strtol(entry->d_name, &end, 10);
    if (end != entry->d_name && *end == 0 && tid > 0) tasks.push_back(tid);
  }
  closedir(dir);
  std::sort(tasks.begin(), tasks.end());
#endif
  return tasks;
}

Bootstrap::Bootstrap(ShmPolicy policy, Observer* observer)
    : policy_(policy), observer_(observer ? observer : &quiet_) {
#if LRB_NATIVE
  // Before any SDK call: only load-time (pre-main) threads can exist here.
  main_tid_ = static_cast<long>(getpid());
  require(static_cast<long>(gettid()) == main_tid_, "bootstrap constructed on the main thread");
  baseline_tasks_ = process_tasks();
#endif
}

void Bootstrap::check_threads(const char* checkpoint) const {
#if LRB_NATIVE
  const std::vector<long> now = process_tasks();
  if (const char* violation = thread_set_violation(baseline_tasks_, now, main_tid_, kSdkPreMainThreads)) {
    const std::string message = std::string(violation) + " at " + checkpoint + " (baseline " +
                                std::to_string(baseline_tasks_.size()) + ", now " +
                                std::to_string(now.size()) + " tasks)";
    require(false, message.c_str());
  }
  require(static_cast<long>(gettid()) == main_tid_, "bootstrap runs on the main thread");
#else
  (void)checkpoint;
#endif
}

Bootstrap::~Bootstrap() {
  // An un-stopped bootstrap is a programming error: tearing down out of order
  // could leave the owner live over unmapped views. Fail closed.
  if (started_) {
    std::fprintf(stderr, "LRB FAIL: bootstrap destroyed while started\n");
    std::abort();
  }
}

rex::runtime::MMIOHandler& Bootstrap::mmio() {
  auto* handler = rex::runtime::MMIOHandler::global_handler();
  require(handler != nullptr, "SDK MMIOHandler singleton retained");
  return *handler;
}

uint8_t* Bootstrap::arena_base() const { return memory_->virtual_membase(); }

void Bootstrap::preflight() {
  // SDK logging: no console or file sink, so ordinary output stays exact.
  rex::LogConfig config{};
  config.log_to_console = std::getenv("LRB_SDK_LOG_CONSOLE") != nullptr;
  rex::InitLogging(config);
  before_ = process_memory();
#if LRB_NATIVE
  snapshot_action(SIGSEGV, pre_segv_);
  snapshot_action(SIGILL, pre_ill_);
  snapshot_action(SIGBUS, pre_bus_);
  require(is_default(pre_segv_) && is_default(pre_ill_) && is_default(pre_bus_),
          "SIGSEGV/SIGILL/SIGBUS unowned before Memory::Initialize");
  stack_t stack{};
  require(sigaltstack(nullptr, &stack) == 0 && (stack.ss_flags & SS_DISABLE),
          "no alternate signal stack before bootstrap");
  // The pinned MapViews uses MAP_FIXED at 2^32 first and cannot detect an
  // existing mapping there; it would silently replace it. Refuse instead.
  require(range_unmapped(read_maps(), kPreferredBase, kPreferredBase + kGuestSpan),
          "guest view range [2^32, 2^32+0x120000000) unmapped before Initialize");
  require(rex::memory::page_size() == 4096, "4 KiB host pages (tested configuration)");
  check_threads("preflight (after SDK logging init)");
#endif
  require(rex::runtime::MMIOHandler::global_handler() == nullptr,
          "no SDK MMIOHandler before Initialize");
}

void Bootstrap::verify_layout() {
  Memory& m = *memory_;
  require(m.virtual_membase() != nullptr &&
              m.physical_membase() == m.virtual_membase() + kPhysicalOffset,
          "physical membase is virtual membase + 4 GiB");
#if LRB_NATIVE
  require(reinterpret_cast<uintptr_t>(m.virtual_membase()) == kPreferredBase,
          "views placed at the first probed base 2^32");
#endif
  struct HeapFact {
    uint32_t base, size, page;
    rex::memory::HeapType type;
  };
  constexpr HeapFact heaps[] = {
      {0x00000000u, 0x40000000u, 4096u, rex::memory::HeapType::kGuestVirtual},
      {0x40000000u, 0x3F000000u, 65536u, rex::memory::HeapType::kGuestVirtual},
      {0x80000000u, 0x10000000u, 65536u, rex::memory::HeapType::kGuestXex},
      {0x90000000u, 0x10000000u, 4096u, rex::memory::HeapType::kGuestXex},
      {0xA0000000u, 0x20000000u, 65536u, rex::memory::HeapType::kGuestPhysical},
      {0xC0000000u, 0x20000000u, 16u * 1024u * 1024u, rex::memory::HeapType::kGuestPhysical},
      {0xE0000000u, 0x1FD00000u, 4096u, rex::memory::HeapType::kGuestPhysical},
  };
  for (const auto& fact : heaps) {
    const auto* heap = m.LookupHeap(fact.base);
    require(heap && heap->heap_base() == fact.base && heap->heap_size() == fact.size &&
                heap->page_size() == fact.page && heap->heap_type() == fact.type,
            "real heap layout matches the pinned SDK map");
  }
  require(m.LookupHeap(0x7F000000u) == nullptr && m.LookupHeap(0xFFD00000u) == nullptr,
          "unmanaged GPU window and top hole have no heap");
  const auto* e_heap = m.LookupHeap(0xE0000000u);
  const uint32_t expected_e_offset = rex::memory::allocation_granularity() > 0x1000 ? 0x1000u : 0u;
  require(e_heap->host_address_offset() == expected_e_offset,
          "0xE0000000 alias host offset follows allocation granularity");
  require(m.GetPhysicalAddress(0xA0001000u) == 0x1000u &&
              m.GetPhysicalAddress(0xC0001000u) == 0x1000u &&
              m.GetPhysicalAddress(0xE0000000u) == 0x1000u &&
              m.GetPhysicalAddress(0x00001000u) == UINT32_MAX,
          "SDK physical address translation (E alias is +0x1000)");
  // 0x8000001C constant written by Initialize through the real xex heap.
  const uint8_t* constant = m.TranslateVirtual(0x8000001Cu);
  require(constant[0] == 0x2a && constant[1] == 0x6e && constant[2] == 0x3f && constant[3] == 0x38,
          "Initialize xex-range constant visible through translation");
  require(host_access(m.TranslateVirtual(0x00000000u)) == PageAccess::kNoAccess,
          "zero page protected by Initialize");
}

// Minimal identity of the SDK object, established before any further check so
// that a later failure still leaves an exact ownership record behind.
void Bootstrap::identify_shared_memory() {
#if LRB_NATIVE
  std::string name = memory_->file_name().string();
  require(!name.empty() && name.find('/') == std::string::npos &&
              name.rfind("xenia_memory_", 0) == 0 && name.size() > 13 &&
              name.find_first_not_of("0123456789", 13) == std::string::npos,
          "SDK shared-memory name is xenia_memory_<ticks>");
  shm_.name = "/" + name;
  struct stat st{};
  require(stat(("/dev/shm" + shm_.name).c_str(), &st) == 0 && S_ISREG(st.st_mode),
          "SDK shm object exists");
  require(st.st_uid == geteuid(), "SDK shm object owned by this user");
  shm_.device = st.st_dev;
  shm_.inode = st.st_ino;
  shm_.apparent_size = uint64_t(st.st_size);
  shm_.allocated_bytes = uint64_t(st.st_blocks) * 512u;
#endif
}

void Bootstrap::verify_shared_memory() {
#if LRB_NATIVE
  Memory& m = *memory_;
  const std::string path = "/dev/shm" + shm_.name;
  const uint64_t gran = rex::memory::allocation_granularity();
  const uint64_t expected = ((0x120000000ull + gran) + gran - 1) / gran * gran;
  require(shm_.apparent_size == expected, "SDK shm apparent size is the full mapping size");
  require(shm_.allocated_bytes < (64ull << 20),
          "sparse shm: only touched pages are allocated (no 4.5 GiB RAM use)");
  // Every SDK view must be backed by THIS object at its exact file offset.
  const auto maps = read_maps();
  const uint64_t base = reinterpret_cast<uintptr_t>(m.virtual_membase());
  const uint64_t mask = ~(gran - 1);
  for (const auto& view : kViews) {
    uint64_t cursor = base + view.start;
    const uint64_t end = base + view.end + 1;
    for (const auto& e : maps) {
      if (e.end <= cursor || e.start >= end) continue;
      require(e.start <= cursor, "view has no unmapped gap");
      require(e.perms[3] == 's' && e.inode == shm_.inode &&
                  e.major == major(shm_.device) && e.minor == minor(shm_.device),
              "view is a shared mapping of the owned shm inode");
      // Adjacent views with contiguous offsets may share one merged VMA.
      require(e.offset + (cursor - e.start) == (view.target & mask) + (cursor - (base + view.start)),
              "view maps the pinned file offset");
      require(e.path.rfind(path, 0) == 0, "view path names the owned shm object");
      cursor = e.end < end ? e.end : end;
    }
    require(cursor == end, "view fully mapped");
  }
  if (policy_ == ShmPolicy::kUnlinkAfterMap) {
    // Unlink only the name proven to back our own views (inode match).
    struct stat again{};
    require(stat(path.c_str(), &again) == 0 && again.st_ino == shm_.inode &&
                again.st_dev == shm_.device,
            "owned shm identity unchanged before early unlink");
    require(unlink(path.c_str()) == 0, "early unlink of the owned shm name");
    errno = 0;
    require(stat(path.c_str(), &again) != 0 && errno == ENOENT, "owned shm name gone");
    shm_.unlinked_early = true;
  }
#endif
}

void Bootstrap::handoff() {
  auto& handler = mmio();
#if LRB_NATIVE
  struct sigaction sdk_segv{}, sdk_ill{};
  snapshot_action(SIGSEGV, sdk_segv);
  snapshot_action(SIGILL, sdk_ill);
  require((sdk_segv.sa_flags & SA_SIGINFO) && (sdk_ill.sa_flags & SA_SIGINFO),
          "Memory::Initialize installed the SDK SIGSEGV/SIGILL thunk");
#endif
  // Remove exactly the SDK thunk registered by MMIOHandler::Install. The
  // MMIOHandler object, its ranges and Memory's callback stay live.
  rex::arch::ExceptionHandler::Uninstall(SdkAccess::exception_thunk(), &handler);
  require(rex::runtime::MMIOHandler::global_handler() == &handler,
          "MMIOHandler singleton survives the handoff");
#if LRB_NATIVE
  verify_restored(SIGSEGV, pre_segv_, "handoff restores the pre-Initialize SIGSEGV action");
  verify_restored(SIGILL, pre_ill_, "handoff restores the pre-Initialize SIGILL action");
  verify_restored(SIGBUS, pre_bus_, "SIGBUS never owned");
  require(lrb_install() == 0, "install the exclusive LRB SIGSEGV owner");
  owner_installed_ = true;
  require(lrb_owns_sigsegv() == 1, "LRB owner is the only live SIGSEGV action");
  check_threads("signal handoff");
  require(lrb_attach() == 0, "attach guarded alternate signal stack");
  attached_ = true;
#endif
}

void Bootstrap::start(const char* ownership_path, const char* mode) {
  require(!started_ && !memory_, "single start");
  ownership_path_ = ownership_path ? ownership_path : "";
  mode_ = mode ? mode : "normal";
  preflight();
  memory_ = std::make_unique<Memory>();
  if (!memory_->Initialize()) {
    // No owner is installed yet and no heap is populated: ~Memory only unmaps
    // the views it created and closes/unlinks the SDK shm name, so a failed
    // Initialize does not leak an unidentifiable /dev/shm object.
    memory_.reset();
    require(false, "real Memory::Initialize (memory released after failure)");
  }
  after_ = process_memory();
  check_threads("after Memory::Initialize");
  identify_shared_memory();
  write_ownership("initialized");
  verify_layout();
  verify_shared_memory();
  handoff();
  scratch_ = std::make_unique<GuestScratch>(*memory_);
  started_ = true;
  write_ownership("started");
}

void Bootstrap::stop() {
  require(started_, "stop after start");
  require(owner_installed_ == bool(LRB_NATIVE) && attached_ == bool(LRB_NATIVE),
          "owner state matches the build (native owner live, ordinary none)");
  const uint8_t* stale_scratch = scratch_->host();
  scratch_->release();
  scratch_.reset();
#if LRB_NATIVE
  require(lrb_detach() == 0, "detach after accesses stop");
  attached_ = false;
  require(lrb_uninstall() == 0, "remove LRB owner before Memory destruction");
  owner_installed_ = false;
  require(lrb_installed() == 0, "owner flag cleared");
  verify_restored(SIGSEGV, pre_segv_, "owner removal restores SIGSEGV");
#endif
  check_threads("before Memory destruction");
  const uintptr_t base = reinterpret_cast<uintptr_t>(memory_->virtual_membase());
  memory_.reset();  // ~MMIOHandler Uninstall is a no-op; views unmapped; shm closed+unlinked.
  require(rex::runtime::MMIOHandler::global_handler() == nullptr,
          "SDK singleton removed with Memory");
  started_ = false;
#if LRB_NATIVE
  verify_restored(SIGSEGV, pre_segv_, "SIGSEGV still default after Memory destruction");
  verify_restored(SIGILL, pre_ill_, "SIGILL still default after Memory destruction");
  stack_t stack{};
  require(sigaltstack(nullptr, &stack) == 0 && (stack.ss_flags & SS_DISABLE),
          "alternate stack removed");
  require(range_unmapped(read_maps(), base, base + kGuestSpan),
          "no guest view remains mapped after teardown");
  require(reinterpret_cast<uintptr_t>(stale_scratch) >= base &&
              reinterpret_cast<uintptr_t>(stale_scratch) < base + kGuestSpan,
          "former scratch address lies in the now-unmapped guest range");
  struct stat st{};
  errno = 0;
  require(stat(("/dev/shm" + shm_.name).c_str(), &st) != 0 && errno == ENOENT,
          "no owned /dev/shm residue after normal teardown");
#else
  (void)base;
  (void)stale_scratch;
#endif
}

void Bootstrap::write_ownership(const char* stage) const {
  if (ownership_path_.empty()) return;
  // Write a sibling temporary file, then rename: the runner never observes a
  // partially written record.
  const std::string temporary = ownership_path_ + ".tmp";
  const char* mode = mode_.c_str();
  std::FILE* file = std::fopen(temporary.c_str(), "w");
  require(file != nullptr, "open ownership record");
  std::fprintf(file,
               "{\"format\":\"LRB_OWNERSHIP_V1\",\"stage\":\"%s\",\"mode\":\"%s\",\"policy\":\"%s\",\"pid\":%lld,"
               "\"shm_name\":\"%s\",\"device\":%" PRIu64 ",\"inode\":%" PRIu64
               ",\"apparent_size\":%" PRIu64 ",\"allocated_bytes\":%" PRIu64
               ",\"unlinked_early\":%s,\"virtual_membase\":%" PRIuPTR
               ",\"vm_size_kib_before\":%" PRIu64 ",\"vm_size_kib_after\":%" PRIu64
               ",\"vm_rss_kib_before\":%" PRIu64 ",\"vm_rss_kib_after\":%" PRIu64 "}\n",
               stage, mode, policy_ == ShmPolicy::kUnlinkAfterMap ? "unlink-after-map" : "sdk-contract",
#if LRB_NATIVE
               static_cast<long long>(getpid()),
#else
               0ll,
#endif
               shm_.name.c_str(), shm_.device, shm_.inode, shm_.apparent_size,
               shm_.allocated_bytes, shm_.unlinked_early ? "true" : "false",
               reinterpret_cast<uintptr_t>(memory_->virtual_membase()), before_.vm_size_kib,
               after_.vm_size_kib, before_.vm_rss_kib, after_.vm_rss_kib);
  require(std::fflush(file) == 0 && std::fclose(file) == 0, "write ownership record");
#if !LRB_NATIVE
  (void)std::remove(ownership_path_.c_str());  // ISO rename does not replace on Windows.
#endif
  require(std::rename(temporary.c_str(), ownership_path_.c_str()) == 0,
          "publish ownership record atomically");
}

[[noreturn]] void Bootstrap::terminal(uintptr_t address) {
  observer_->before_terminal(address);
#if LRB_NATIVE
  lrb_terminal();
#endif
  std::abort();
}

bool Bootstrap::dispatch(uintptr_t host, bool is_write) {
  Memory& m = *memory_;
  const uintptr_t base = reinterpret_cast<uintptr_t>(m.virtual_membase());
  require(host >= base && host < base + kGuestSpan, "dispatch inside the guest views");
  if (host < reinterpret_cast<uintptr_t>(m.physical_membase()) &&
      m.LookupVirtualMappedRange(m.HostToGuestVirtual(reinterpret_cast<void*>(host))))
    terminal(host);  // The SDK would decode a host instruction from a null context.
  rex::arch::HostThreadContext context{};
  Exception exception{};
  exception.InitializeAccessViolation(&context, host, is_write ? Operation::kWrite : Operation::kRead);
  bool handled = false;
  try {
    handled = (mmio().*SdkAccess::exception_callback())(&exception);
  } catch (...) {
    observer_->consumer_exception(host, std::current_exception());
    terminal(host);
  }
  if (handled) ++consumed_; else ++declined_;
  return handled;
}

#if LRB_NATIVE
// `before` is this thread's admitted-fault total; the transport's per-thread
// counter must have advanced by exactly one for this access.
bool Bootstrap::admitted(uintptr_t host, bool is_write, unsigned before) const {
  lrb_fault fault{};
  return lrb_last_fault(&fault) && fault.signal_number == SIGSEGV &&
         fault.signal_code == SEGV_ACCERR && fault.address == host &&
         fault.instruction == reinterpret_cast<uintptr_t>(is_write ? lrb_write_site : lrb_read_site) &&
         fault.operation == (is_write ? LRB_WRITE : LRB_READ) && fault.on_altstack != 0 &&
         fault.count == before + 1;
}
#endif

AccessResult Bootstrap::checked_load32(uint32_t guest, uint32_t& value, DeclinedFault* declined) {
  require(started_ && (guest & 3u) == 0, "checked load is aligned and started");
  uint32_t mmio_value = 0;
  if (mmio().CheckLoad(guest, &mmio_value)) {  // MMIO first: no memory touch.
    value = mmio_value;
    return AccessResult::kMmio;
  }
  uint8_t* host = memory_->TranslateVirtual(guest);
#if LRB_NATIVE
  uint32_t raw = 0;
  lrb_status status = lrb_read32(arena_base(), arena_size(), host, &raw);
  if (status == LRB_OK) { value = raw; return AccessResult::kMemory; }
  const uintptr_t address = reinterpret_cast<uintptr_t>(host);
  if (status != LRB_FAULT || !admitted(address, false, admitted_faults_)) terminal(address);
  ++admitted_faults_;
  if (dispatch(address, false)) {
    observer_->claimed_repair(address);
    status = lrb_read32(arena_base(), arena_size(), host, &raw);  // One fresh read only.
    if (status == LRB_OK) { value = raw; return AccessResult::kRepaired; }
    if (status == LRB_FAULT && admitted(address, false, admitted_faults_)) {
      ++admitted_faults_;
      observer_->retry_fault(address);
    }
    terminal(address);
  }
  observer_->declined(address);
  if (declined) *declined = {address, guest, false};
  return AccessResult::kDeclined;
#else
  // Ordinary build: no hardware fault capture. A no-access page is reported
  // as a synthetic decline through the same real SDK dispatch.
  const uintptr_t address = reinterpret_cast<uintptr_t>(host);
  if (host_access(host) == PageAccess::kNoAccess) {
    if (dispatch(address, false)) terminal(address);  // Read watches unsupported.
    if (declined) *declined = {address, guest, false};
    return AccessResult::kDeclined;
  }
  std::memcpy(&value, host, sizeof(value));
  return AccessResult::kMemory;
#endif
}

AccessResult Bootstrap::checked_store32(uint32_t guest, uint32_t value) {
  require(started_ && (guest & 3u) == 0, "checked store is aligned and started");
  if (mmio().CheckStore(guest, value)) return AccessResult::kMmio;
  uint8_t* host = memory_->TranslateVirtual(guest);
  const uintptr_t address = reinterpret_cast<uintptr_t>(host);
#if LRB_NATIVE
  lrb_status status = lrb_write32(arena_base(), arena_size(), host, value);
  if (status == LRB_OK) return AccessResult::kMemory;
  if (status != LRB_FAULT || !admitted(address, true, admitted_faults_)) terminal(address);
  ++admitted_faults_;
  if (!dispatch(address, true)) terminal(address);  // Guest-write records unsupported.
  observer_->claimed_repair(address);
  status = lrb_write32(arena_base(), arena_size(), host, value);  // One fresh store only.
  if (status == LRB_OK) return AccessResult::kRepaired;
  if (status == LRB_FAULT && admitted(address, true, admitted_faults_)) {
    ++admitted_faults_;
    observer_->retry_fault(address);
  }
  terminal(address);
#else
  const PageAccess access = host_access(host);
  if (access != PageAccess::kReadWrite) {
    if (!dispatch(address, true) || host_access(host) != PageAccess::kReadWrite) terminal(address);
    observer_->claimed_repair(address);
    std::memcpy(host, &value, sizeof(value));
    return AccessResult::kRepaired;
  }
  std::memcpy(host, &value, sizeof(value));
  return AccessResult::kMemory;
#endif
}

}  // namespace lrb
