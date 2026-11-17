// LRB acceptance executable. Uses only synthetic guest data and the real
// pinned SDK memory system; never loads game data or generated game code.
#include "lrb_bootstrap.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <string_view>
#include <vector>

#include <rex/memory/utils.h>

#if LRB_NATIVE
#include <signal.h>
#include <sys/resource.h>
#include <unistd.h>
#include "lrb_owner.h"
#endif

namespace {
using lrb::AccessResult;
using lrb::require;
using rex::memory::PageAccess;

constexpr uint32_t kGuestPc = 0x82001234u;      // Synthetic; no generated code.
constexpr uint32_t kMmioBase = 0x7FC80000u;     // Inside the unmanaged 0x7F window.
constexpr uint32_t kMmioMask = 0xFFFF0000u;
constexpr uint32_t kMmioValue = 0x1234ABCDu;
constexpr uint32_t kAliasVa = 0xA4000000u;      // vA 64 KiB physical alias allocation.
constexpr uint32_t kAliasPhysical = 0x04000000u;
constexpr uint32_t kWatchOffset = 0x2000u;
constexpr uint32_t kGpuPhysical = 0x00200000u;  // Committed by Initialize via vC.

enum class Inject { none, throw_sentinel, false_repair };
struct Sentinel final {};

struct State {
  unsigned invalidations = 0, mmio_reads = 0, mmio_writes = 0, records = 0;
  uint32_t last_mmio_store = 0, inv_address = 0, inv_length = 0;
  bool inv_exact = true;
  Inject inject = Inject::none;
  rex::memory::BaseHeap* alias_heap = nullptr;
};
State g_state;

class Witness final : public lrb::Observer {
 public:
  Witness(const char* mode, const char* token) : mode_(mode) {
    valid_ = token && std::strlen(token) == 32;
    for (unsigned i = 0; valid_ && i < 32; ++i)
      valid_ = (token[i] >= '0' && token[i] <= '9') || (token[i] >= 'a' && token[i] <= 'f');
    if (valid_) std::memcpy(token_, token, 33);
  }
  bool valid() const { return valid_; }
  void bind(lrb::Bootstrap* bootstrap) { bootstrap_ = bootstrap; }
  void emit(const char* phase, uintptr_t address) {
    if (!valid_ || !bootstrap_) return;
    std::array<char, 256> line{};
    const int n = std::snprintf(line.data(), line.size(),
        "LRB_GATE_V1 token=%s mode=%s phase=%s faults=%u consumed=%u invalidations=%u "
        "records=%u address=0x%llx\n",
        token_, mode_, phase, bootstrap_->admitted_faults(), bootstrap_->consumed_dispatches(),
        g_state.invalidations, g_state.records, static_cast<unsigned long long>(address));
    if (n > 0 && static_cast<size_t>(n) < line.size()) {
      (void)std::fwrite(line.data(), 1, static_cast<size_t>(n), stderr);
      (void)std::fflush(stderr);
    }
  }
  void claimed_repair(uintptr_t a) override { if (g_state.inject == Inject::false_repair) emit("claimed", a); }
  void retry_fault(uintptr_t a) override { emit("retry_fault", a); }
  void consumer_exception(uintptr_t a, std::exception_ptr error) override {
    try {
      std::rethrow_exception(error);
    } catch (const Sentinel&) {
      emit("caught", a);  // Only the private sentinel is acknowledged.
    } catch (...) {
    }
  }
  void declined(uintptr_t a) override { if (expect_decline_) emit("declined", a); }
  void before_terminal(uintptr_t a) override { emit("terminal", a); }
  bool expect_decline_ = false;
  uintptr_t injected_address = 0;

 private:
  const char* mode_;
  char token_[33] = {};
  bool valid_ = false;
  lrb::Bootstrap* bootstrap_ = nullptr;
};
Witness* g_witness = nullptr;

uint32_t mmio_read(void*, void* opaque, uint32_t address) {
  auto& s = *static_cast<State*>(opaque);
  require((address & kMmioMask) == kMmioBase, "MMIO read callback address");
  ++s.mmio_reads;
  return kMmioValue;
}
void mmio_write(void*, void* opaque, uint32_t address, uint32_t value) {
  auto& s = *static_cast<State*>(opaque);
  require((address & kMmioMask) == kMmioBase, "MMIO write callback address");
  ++s.mmio_writes;
  s.last_mmio_store = value;
}

std::pair<uint32_t, uint32_t> invalidated(void* opaque, uint32_t physical, uint32_t length,
                                          bool exact) {
  auto& s = *static_cast<State*>(opaque);
  ++s.invalidations;
  s.inv_address = physical;
  s.inv_length = length;
  s.inv_exact = exact;
  if (s.inject == Inject::throw_sentinel) {
    if (g_witness) g_witness->emit("injected", g_witness->injected_address);
    throw Sentinel{};
  }
  if (s.inject == Inject::false_repair) {
    // Test-only false repair through the real SDK: drop guest write permission
    // so TriggerCallbacks consumes the fault but cannot unprotect the page.
    require(s.alias_heap->Protect(kAliasVa, 0x10000u, rex::memory::kMemoryProtectRead),
            "injected false repair via real PhysicalHeap::Protect");
  }
  return {physical, length};
}

uint32_t word(const uint8_t* p) {
  uint32_t v;
  std::memcpy(&v, p, sizeof(v));
  return v;
}
void put(uint8_t* p, uint32_t v) { std::memcpy(p, &v, sizeof(v)); }

struct Alias {
  uint8_t *a, *raw, *c, *e;
};
Alias alias_hosts(rex::memory::Memory& m, uint32_t offset) {
  const uint32_t physical = kAliasPhysical + offset;
  require(m.GetPhysicalAddress(kAliasVa + offset) == physical &&
              m.GetPhysicalAddress(0xC0000000u + physical) == physical &&
              m.GetPhysicalAddress(0xE0000000u + physical - 0x1000u) == physical,
          "A/C/E alias guest addresses translate to one physical address");
  return {m.TranslateVirtual(kAliasVa + offset), m.TranslatePhysical(physical),
          m.TranslateVirtual(0xC0000000u + physical),
          m.TranslateVirtual(0xE0000000u + physical - 0x1000u)};
}

void prepare_alias(lrb::Bootstrap& bs) {
  auto& m = bs.memory();
  g_state.alias_heap = m.LookupHeap(kAliasVa);
  require(g_state.alias_heap &&
              g_state.alias_heap->AllocFixed(kAliasVa, 0x10000u, 0x10000u,
                                             rex::memory::kMemoryAllocationReserve |
                                                 rex::memory::kMemoryAllocationCommit,
                                             rex::memory::kMemoryProtectRead |
                                                 rex::memory::kMemoryProtectWrite),
          "real vA physical allocation at a fixed alias address");
  require(m.GetPhysicalAddress(kAliasVa) == kAliasPhysical, "vA allocation physical address");
}

void test_aliases(lrb::Bootstrap& bs) {
  auto& m = bs.memory();
  const Alias h = alias_hosts(m, 0x100u);
  require(h.a != h.raw && h.a != h.c && h.a != h.e && h.raw != h.c && h.raw != h.e && h.c != h.e,
          "four distinct host views of one physical word");
  put(h.raw, 0x11223344u);
  require(word(h.a) == 0x11223344u && word(h.c) == 0x11223344u && word(h.e) == 0x11223344u,
          "raw physical write visible through A/C/E aliases");
  put(h.e, 0x55667788u);
  require(word(h.a) == 0x55667788u && word(h.raw) == 0x55667788u && word(h.c) == 0x55667788u,
          "E alias write visible through A/C/raw");
  // GPU writeback window: 0x7F000000 view maps the first 16 MiB of physical.
  uint8_t* raw = m.TranslatePhysical(kGpuPhysical);
  uint8_t* window = m.virtual_membase() + 0x7F000000u + kGpuPhysical;
  uint8_t* c = m.TranslateVirtual(0xC0000000u + kGpuPhysical);
  put(window, 0x0BADF00Du);
  require(word(raw) == 0x0BADF00Du && word(c) == 0x0BADF00Du,
          "0x7F GPU window aliases physical memory");
  uint32_t value = 0;
  require(bs.checked_load32(kAliasVa + 0x100u, value, nullptr) == AccessResult::kMemory &&
              value == 0x55667788u && bs.admitted_faults() == 0,
          "checked load of a plain alias word needs no fault");
}

void test_mmio(lrb::Bootstrap& bs) {
  auto& m = bs.memory();
  require(m.AddVirtualMappedRange(kMmioBase, kMmioMask, 0xFFFFu, &g_state, mmio_read, mmio_write),
          "real Memory::AddVirtualMappedRange");
  const auto* range = m.LookupVirtualMappedRange(kMmioBase + 0x10u);
  require(range && range->address == kMmioBase && range->mask == kMmioMask &&
              range->read == mmio_read && range->write == mmio_write,
          "real MMIO range lookup");
  require(m.LookupVirtualMappedRange(kAliasVa) == nullptr, "non-MMIO address has no range");
  require(lrb::host_access(m.TranslateVirtual(kMmioBase)) == PageAccess::kNoAccess,
          "MMIO host window is no-access");
  uint32_t value = 0;
  require(bs.mmio().CheckLoad(kMmioBase + 0x10u, &value) && value == kMmioValue &&
              g_state.mmio_reads == 1,
          "direct SDK CheckLoad consumes once");
  require(bs.mmio().CheckStore(kMmioBase + 0x14u, 0x10203040u) && g_state.mmio_writes == 1 &&
              g_state.last_mmio_store == 0x10203040u,
          "direct SDK CheckStore consumes once");
  value = 0xFEEDFACEu;
  require(!bs.mmio().CheckLoad(kAliasVa, &value) && value == 0xFEEDFACEu &&
              !bs.mmio().CheckStore(kAliasVa, 1) && g_state.mmio_reads == 1 &&
              g_state.mmio_writes == 1,
          "non-MMIO address declines without callbacks or output writes");
  const unsigned faults = bs.admitted_faults(), invalidations = g_state.invalidations;
  value = 0;
  require(bs.checked_load32(kMmioBase + 0x20u, value, nullptr) == AccessResult::kMmio &&
              value == kMmioValue && g_state.mmio_reads == 2,
          "checked load consumes MMIO first");
  require(bs.checked_store32(kMmioBase + 0x24u, 0x0A0B0C0Du) == AccessResult::kMmio &&
              g_state.mmio_writes == 2 && g_state.last_mmio_store == 0x0A0B0C0Du,
          "checked store consumes MMIO first");
  require(bs.admitted_faults() == faults && g_state.invalidations == invalidations &&
              bs.consumed_dispatches() == 0,
          "MMIO ordering: no protected-window fault, watch or SDK dispatch");
}

void arm_watch(lrb::Bootstrap& bs) {
  auto& m = bs.memory();
  const uint32_t page = static_cast<uint32_t>(rex::memory::page_size());
  m.EnablePhysicalMemoryAccessCallbacks(kAliasPhysical + kWatchOffset, page, true, false);
  const Alias h = alias_hosts(m, kWatchOffset);
  require(lrb::host_access(h.a) == PageAccess::kReadOnly, "watch protects the allocating alias");
  require(lrb::host_access(h.raw) == PageAccess::kReadWrite &&
              lrb::host_access(h.c) == PageAccess::kReadWrite &&
              lrb::host_access(h.e) == PageAccess::kReadWrite,
          "raw/C/E views stay writable (SDK: only allocated alias pages are watched)");
  require(lrb::host_page_watched(m.LookupHeap(kAliasVa), kAliasVa + kWatchOffset) &&
              !lrb::host_page_watched(m.LookupHeap(0xC0000000u),
                                      0xC0000000u + kAliasPhysical + kWatchOffset) &&
              !lrb::host_page_watched(m.LookupHeap(0xE0000000u),
                                      0xE0000000u + kAliasPhysical + kWatchOffset - 0x1000u),
          "watch flag set on the A alias only");
}

void test_watch(lrb::Bootstrap& bs) {
  auto& m = bs.memory();
  const uint32_t page = static_cast<uint32_t>(rex::memory::page_size());
  const uint32_t va = kAliasVa + kWatchOffset;
  arm_watch(bs);
  const Alias h = alias_hosts(m, kWatchOffset);
  // Physical-view stores bypass watches by SDK design (data-provider path).
#if LRB_NATIVE
  require(lrb_write32(bs.arena_base(), bs.arena_size(), h.raw, 0x01010101u) == LRB_OK,
          "raw physical checked store does not fault");
#else
  put(h.raw, 0x01010101u);
#endif
  require(word(h.a) == 0x01010101u && g_state.invalidations == 0 &&
              lrb::host_access(h.a) == PageAccess::kReadOnly &&
              lrb::host_page_watched(m.LookupHeap(kAliasVa), va),
          "bypass write leaves the watch armed and uninvoked");
  const unsigned faults = bs.admitted_faults();
  require(bs.checked_store32(va, 0xCAFEF00Du) == AccessResult::kRepaired,
          "protected alias store repaired through the real SDK path");
#if LRB_NATIVE
  require(bs.admitted_faults() == faults + 1, "exactly one genuine protected-memory fault");
#else
  (void)faults;
#endif
  require(bs.consumed_dispatches() == 1 && g_state.invalidations == 1,
          "exactly one deferred repair and one invalidation");
  require(g_state.inv_address == kAliasPhysical + kWatchOffset && g_state.inv_length == page &&
              !g_state.inv_exact,
          "real Memory callback reports the watched physical page");
  require(!lrb::host_page_watched(m.LookupHeap(kAliasVa), va) &&
              lrb::host_access(h.a) == PageAccess::kReadWrite,
          "repair clears the watch and restores write access");
  require(word(h.a) == 0xCAFEF00Du && word(h.raw) == 0xCAFEF00Du && word(h.e) == 0xCAFEF00Du &&
              word(h.c) == 0xCAFEF00Du,
          "fresh store committed once, visible through every alias");
  require(bs.checked_store32(va, 0xD00DFEEDu) == AccessResult::kMemory &&
              word(h.raw) == 0xD00DFEEDu && g_state.invalidations == 1 &&
              bs.consumed_dispatches() == 1,
          "later store needs no repair and causes no duplicate invalidation");
#if LRB_NATIVE
  require(bs.admitted_faults() == faults + 1, "no further fault after repair");
#endif
}

uint32_t no_access_page(lrb::Bootstrap& bs) {
  auto* heap = bs.memory().LookupHeapByType(false, 4096);
  uint32_t va = 0;
  require(heap->Alloc(4096, 4096,
                      rex::memory::kMemoryAllocationReserve | rex::memory::kMemoryAllocationCommit,
                      rex::memory::kMemoryProtectNoAccess, false, &va) &&
              va != 0,
          "real virtual-heap no-access allocation");
  require(lrb::host_access(bs.memory().TranslateVirtual(va)) == PageAccess::kNoAccess,
          "no-access guest page is host no-access");
  return va;
}

void verify_record(lrb::Bootstrap& bs, uint32_t va) {
  auto& s = bs.scratch();
  s.verify_owned();
  const uint32_t g = s.guest(), r = lrb::GuestScratch::kRecord;
  require(s.be32(lrb::GuestScratch::kPointers) == g + r && s.be32(lrb::GuestScratch::kPointers + 4) == 0,
          "guest EXCEPTION_POINTERS in owned scratch");
  require(s.be32(r) == lrb::kGuestAccessViolation && s.be32(r + 4) == 0 && s.be32(r + 8) == 0 &&
              s.be32(r + 12) == kGuestPc && s.be32(r + 16) == 2 && s.be32(r + 20) == 0 &&
              s.be32(r + 24) == va,
          "M4 access-violation record serialized in guest memory");
  for (uint32_t o = r + 28; o < r + 80; o += 4) require(s.be32(o) == 0, "unused record fields zero");
  require(s.host()[lrb::GuestScratch::kPointers - 1] == 0xA5 && s.host()[r + 80] == 0xA5,
          "record writes stay inside their slots (canaries intact)");
}

// Regression for the first native retry ("single-threaded process before
// bootstrap"): the pinned runtime starts one TimerQueue dispatcher before main.
void test_thread_policy() {
  using V = std::vector<long>;
  constexpr long kMain = 100;
  const auto ok = [](const V& base, const V& now, long main_tid) {
    return lrb::thread_set_violation(base, now, main_tid, lrb::kSdkPreMainThreads) == nullptr;
  };
  require(lrb::kSdkPreMainThreads == 1, "exactly one documented pre-main SDK thread");
  require(ok({100, 101}, {100, 101}, kMain), "main + SDK dispatcher, unchanged, is accepted");
  require(!ok({100}, {100}, kMain), "missing SDK dispatcher is not silently accepted");
  require(!ok({100, 101, 102}, {100, 101, 102}, kMain), "an extra pre-main thread is refused");
  require(!ok({100, 101}, {100, 101, 103}, kMain), "a thread created during the bootstrap is refused");
  require(!ok({100, 101}, {100, 102}, kMain), "a replaced thread is refused");
  require(!ok({100, 101}, {100}, kMain), "a thread exiting during the bootstrap is refused");
  require(!ok({101, 102}, {101, 102}, kMain), "a task set without the main thread is refused");
}

void test_declined(lrb::Bootstrap& bs) {
  const uint32_t va = no_access_page(bs);
  auto& s = bs.scratch();
  std::memset(s.host(), 0xA5, lrb::GuestScratch::kSize);
  const unsigned declined = bs.declined_dispatches(), consumed = bs.consumed_dispatches();
  uint32_t value = 0xDECAFBADu;
  lrb::DeclinedFault fault{};
  require(bs.checked_load32(va, value, &fault) == AccessResult::kDeclined && value == 0xDECAFBADu &&
              fault.guest_address == va && !fault.is_write &&
              fault.host_address == reinterpret_cast<uintptr_t>(bs.memory().TranslateVirtual(va)),
          "real Memory callback declines a virtual-heap read; output untouched");
  require(bs.declined_dispatches() == declined + 1 && bs.consumed_dispatches() == consumed,
          "declined read is never reported as repaired");
  s.record_read_violation(kGuestPc, va);
  ++g_state.records;
  verify_record(bs, va);
  uint32_t released = 0;
  require(bs.memory().LookupHeap(va)->Release(va, &released) && released == 4096,
          "release the no-access test page");
}

#if LRB_NATIVE
[[noreturn]] void run_fatal(lrb::Bootstrap& bs, std::string_view mode) {
  if (mode == "callback-failure" || mode == "repair-failure") {
    prepare_alias(bs);
    arm_watch(bs);
    const uint32_t va = kAliasVa + kWatchOffset;
    g_witness->injected_address = reinterpret_cast<uintptr_t>(bs.memory().TranslateVirtual(va));
    g_state.inject = mode == "callback-failure" ? Inject::throw_sentinel : Inject::false_repair;
    (void)bs.checked_store32(va, 0x77777777u);
    require(false, "fatal store returned");
  }
  if (mode == "declined-unhandled") {
    const uint32_t va = no_access_page(bs);
    std::memset(bs.scratch().host(), 0xA5, lrb::GuestScratch::kSize);
    g_witness->expect_decline_ = true;
    uint32_t value = 0;
    lrb::DeclinedFault fault{};
    require(bs.checked_load32(va, value, &fault) == AccessResult::kDeclined, "declined read");
    bs.scratch().record_read_violation(kGuestPc, va);
    ++g_state.records;
    verify_record(bs, va);
    g_witness->emit("recorded", fault.host_address);
    bs.terminal(fault.host_address);  // No guest handler exists: unhandled is terminal.
  }
  if (mode == "unadmitted") {
    const uint32_t va = no_access_page(bs);
    auto* host = reinterpret_cast<volatile uint32_t*>(bs.memory().TranslateVirtual(va));
    g_witness->emit("begin", reinterpret_cast<uintptr_t>(host));
    *host = 1;  // Not a checked access: the owner must terminate in signal context.
    require(false, "unadmitted store returned");
  }
  if (mode == "wrong-site") {
    const uint32_t va = no_access_page(bs);
    const void* host = bs.memory().TranslateVirtual(va);
    g_witness->emit("begin", reinterpret_cast<uintptr_t>(host));
    // Armed for this exact address, but the fault comes from a non-admitted site.
    lrb_test_wrong_site(bs.arena_base(), bs.arena_size(), host);
    require(false, "wrong-site access returned");
  }
  require(false, "unknown fatal mode");
  std::abort();
}
#endif
}  // namespace

int main(int argc, char** argv) {
  const std::string_view mode = argc > 1 ? argv[1] : "normal";
  require(argc <= 2, "one optional mode");
#if LRB_NATIVE
  const bool fatal = mode == "callback-failure" || mode == "repair-failure" ||
                     mode == "declined-unhandled" || mode == "unadmitted" || mode == "wrong-site";
  require(fatal || mode == "normal" || mode == "leak-probe", "unsupported native mode");
  const rlimit no_core{0, 0};
  require(setrlimit(RLIMIT_CORE, &no_core) == 0, "disable core dumps for fatal modes");
#else
  const bool fatal = false;
  require(mode == "normal", "ordinary build supports normal mode only");
#endif
  Witness witness(mode.data(), std::getenv("LRB_GATE_TOKEN"));
  if (fatal) require(witness.valid(), "fatal modes require a 32-hex LRB_GATE_TOKEN");
  g_witness = &witness;
  lrb::Bootstrap bs(fatal ? lrb::ShmPolicy::kUnlinkAfterMap : lrb::ShmPolicy::kSdkContract,
                    fatal ? &witness : nullptr);
  witness.bind(&bs);
  bs.start(std::getenv("LRB_OWNERSHIP_FILE"), mode.data());
  void* handle = bs.memory().RegisterPhysicalMemoryInvalidationCallback(invalidated, &g_state);
  require(handle != nullptr, "real invalidation callback registration");
#if LRB_NATIVE
  if (mode == "leak-probe") {
    // Abnormal termination with the SDK shm name still linked (records the
    // crash-leak behaviour; the runner removes only this inode-matched object).
    std::fflush(nullptr);
    raise(SIGKILL);
  }
  if (fatal) run_fatal(bs, mode);
#endif
  test_thread_policy();
  prepare_alias(bs);
  test_aliases(bs);
  test_mmio(bs);
  test_watch(bs);
  test_declined(bs);
#if LRB_NATIVE
  require(bs.admitted_faults() == 2, "exactly two admitted faults (watch store + declined read)");
#endif
  require(bs.consumed_dispatches() == 1 && bs.declined_dispatches() == 1 &&
              g_state.invalidations == 1 && g_state.records == 1,
          "one repair, one decline, one invalidation, one record");
  bs.memory().UnregisterPhysicalMemoryInvalidationCallback(handle);
  const auto before = bs.before_initialize(), after = bs.after_initialize();
  const auto shm = bs.shm();
  bs.stop();
  std::printf("LRB_MEMORY vm_size_kib_before=%llu vm_size_kib_after=%llu vm_rss_kib_before=%llu "
              "vm_rss_kib_after=%llu shm_apparent=%llu shm_allocated=%llu\n",
              (unsigned long long)before.vm_size_kib, (unsigned long long)after.vm_size_kib,
              (unsigned long long)before.vm_rss_kib, (unsigned long long)after.vm_rss_kib,
              (unsigned long long)shm.apparent_size, (unsigned long long)shm.allocated_bytes);
  std::printf("LRB PASS checks=%u mode=%.*s native=%d\n", lrb::checks(),
              static_cast<int>(mode.size()), mode.data(), LRB_NATIVE);
  return 0;
}
