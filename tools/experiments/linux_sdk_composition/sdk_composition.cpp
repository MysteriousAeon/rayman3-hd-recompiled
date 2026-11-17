// Isolated ReXGlue consumer composition. Synthetic mappings only; never launches the game.
#include <filesystem>
#include <rex/exception_handler.h>
#include <rex/memory/utils.h>
#include <rex/system/mmio_handler.h>
#include <rex/system/xmemory.h>
#include "../linux_guest_integration/record_bridge.h"
#ifndef LSC_ORDINARY_ONLY
#include "transport.h"
#endif
#ifdef LSC_TERMINAL_DIAGNOSTICS
#include "terminal_trace.h"
#endif

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <functional>
#include <memory>
#include <mutex>
#include <span>
#include <stdexcept>
#include <string_view>
#include <string_view>
#include <utility>
#include <vector>

#ifndef LSC_ORDINARY_ONLY
#include <signal.h>
#include <sys/resource.h>
#include <unistd.h>
#endif

namespace {
using Exception = rex::arch::Exception;
using Operation = Exception::AccessViolationOperation;
using Handler = rex::runtime::MMIOHandler;
using Memory = rex::memory::Memory;
using PhysicalHeap = rex::memory::PhysicalHeap;
using PageAccess = rex::memory::PageAccess;

unsigned checks = 0;
void check(bool condition, const char* message) {
  ++checks;
  if (condition) return;
  std::fprintf(stderr, "SDK_COMPOSITION FAIL: %s\n", message);
  std::exit(2);
}

class Mapping final {
 public:
  explicit Mapping(size_t size) : size_(size) {
    base_ = static_cast<uint8_t*>(rex::memory::AllocFixed(
        nullptr, size_, rex::memory::AllocationType::kReserve,
        PageAccess::kNoAccess));
    check(base_ != nullptr, "SDK synthetic mapping reservation");
  }
  ~Mapping() {
    if (!base_) return;
#if REX_PLATFORM_WIN32
    constexpr size_t release_length = 0;
#else
    const size_t release_length = size_;
#endif
    if (!rex::memory::DeallocFixed(base_, release_length,
                                   rex::memory::DeallocationType::kRelease))
      std::abort();
  }
  Mapping(const Mapping&) = delete;
  Mapping& operator=(const Mapping&) = delete;
  uint8_t* base() const { return base_; }
  size_t size() const { return size_; }

 private:
  size_t size_;
  uint8_t* base_ = nullptr;
};

struct CallbackState {
  Memory& memory;
  PhysicalHeap& heap;
  uint8_t* base;
  size_t size;
  size_t page;
  unsigned mmio_reads = 0;
  unsigned mmio_writes = 0;
  unsigned invalidations = 0;
  unsigned access_callbacks = 0;
  unsigned guest_dispatches = 0;
  uint32_t last_mmio_store = 0;
  uint32_t mmio_guest_ea = 0;
  uint32_t watched_ea = 0;
  bool decline_write_repair = false;
  bool fail_next_invalidation = false;
  bool recursive_test = false;
  bool recursive_rejected = false;
  bool dispatch_active = false;
#ifdef LSC_TERMINAL_DIAGNOSTICS
  lsc_gate::Witness* terminal_witness = nullptr;
#endif
};

constexpr uint32_t kMmioAddress = 0x7f000000u;
constexpr uint32_t kMmioValue = 0x1234abcdu;
constexpr uint32_t kGuestPc = 0x82001234u;
#ifndef LSC_ORDINARY_ONLY
constexpr uint32_t kGuestLabel = 0x82001300u;
#endif

uint32_t host_to_guest(const void* opaque, const void* host_address) {
  const auto& state = *static_cast<const CallbackState*>(opaque);
  return static_cast<uint32_t>(reinterpret_cast<uintptr_t>(host_address) -
                               reinterpret_cast<uintptr_t>(state.base));
}

class MMIOAccess final : public Handler {
 public:
  using ExceptionCallbackType = bool (Handler::*)(Exception*);
  static ExceptionCallbackType exception_callback() {
    return &MMIOAccess::ExceptionCallback;
  }
  static rex::arch::ExceptionHandler::Handler exception_thunk() {
    return &MMIOAccess::ExceptionCallbackThunk;
  }
};

uint32_t mmio_read(void*, void* opaque, uint32_t address) {
  auto& state = *static_cast<CallbackState*>(opaque);
  check(address == kMmioAddress || address == state.mmio_guest_ea,
        "real MMIO read guest address");
  ++state.mmio_reads;
  return kMmioValue;
}

void mmio_write(void*, void* opaque, uint32_t address, uint32_t value) {
  auto& state = *static_cast<CallbackState*>(opaque);
  check(address == kMmioAddress || address == state.mmio_guest_ea,
        "real MMIO write guest address");
  ++state.mmio_writes;
  state.last_mmio_store = value;
}

std::pair<uint32_t, uint32_t> invalidation_callback(
    void* opaque, uint32_t physical_address, uint32_t length, bool exact_range) {
  auto& state = *static_cast<CallbackState*>(opaque);
  ++state.invalidations;
  check(exact_range, "one page write-watch exact range");
  check(physical_address == state.watched_ea && length == state.page,
        "SDK invalidation callback range");
  if (state.fail_next_invalidation) {
    state.fail_next_invalidation = false;
#ifdef LSC_TERMINAL_DIAGNOSTICS
    check(state.terminal_witness != nullptr,
          "diagnostic invalidator has an active terminal witness");
    check(state.terminal_witness->consumers(state.access_callbacks,
                                             state.invalidations),
          "diagnostic invalidator counter deltas are valid");
    check(state.terminal_witness->emit("injected"),
          "diagnostic injected invalidator witness");
    throw lsc_gate::InjectedInvalidation{};
#else
    throw std::runtime_error("fixture invalidation callback failure");
#endif
  }
  return {physical_address, length};
}

bool access_violation(std::unique_lock<std::recursive_mutex> lock,
                      void* opaque, void* host_address, bool is_write) {
  auto& state = *static_cast<CallbackState*>(opaque);
  ++state.access_callbacks;
  check(lock.owns_lock(), "SDK supplies its locked callback region");
  const uintptr_t base = reinterpret_cast<uintptr_t>(state.base);
  const uintptr_t host = reinterpret_cast<uintptr_t>(host_address);
  check(host >= base && host - base < state.size,
        "SDK callback host pointer is in the owned mapping");
  if (state.dispatch_active) return false;
  if (state.recursive_test && !state.dispatch_active) {
    state.dispatch_active = true;
    rex::arch::HostThreadContext nested_context{};
    Exception nested{};
    nested.InitializeAccessViolation(&nested_context, host, Operation::kWrite);
    state.recursive_rejected =
        !(Handler::global_handler()->*MMIOAccess::exception_callback())(&nested);
    state.dispatch_active = false;
  }
  if (!is_write) return false;  // PhysicalHeap read watches are unsupported.
  if (state.decline_write_repair) return true;  // Deliberately false repair for fatal subprocess.
  const uint32_t guest_address = static_cast<uint32_t>(host - base);
  return state.heap.TriggerCallbacks(std::move(lock), guest_address, 1, true,
                                     true, true);
}

void dispatch_sdk_access(Handler& handler, uintptr_t address, Operation operation,
                         bool& handled) {
  rex::arch::HostThreadContext context{};
  Exception exception{};
  exception.InitializeAccessViolation(&context, address, operation);
  handled = (handler.*MMIOAccess::exception_callback())(&exception);
}

#ifndef LSC_ORDINARY_ONLY
struct PriorAction {
  struct sigaction segv{};
  struct sigaction ill{};
};

void require_default(const struct sigaction& action, const char* name) {
  check(action.sa_handler == SIG_DFL, name);
}

void verify_restored_action(int signal_number, const struct sigaction& before,
                            const char* message) {
  struct sigaction after{};
  check(sigaction(signal_number, nullptr, &after) == 0,
        "query restored signal disposition");
  check(after.sa_handler == before.sa_handler, message);
  // glibc may normalize its private x86-64 SA_RESTORER bit while round-tripping
  // a default action. Compare all POSIX-visible action flags exactly.
  constexpr unsigned long kLibcSaRestorer = 0x04000000ul;
  check((static_cast<unsigned long>(after.sa_flags) & ~kLibcSaRestorer) ==
            (static_cast<unsigned long>(before.sa_flags) & ~kLibcSaRestorer),
        "restored signal semantic flags exactly (ignoring libc SA_RESTORER)");
  for (int candidate = 1; candidate < NSIG; ++candidate) {
    if (candidate == SIGKILL || candidate == SIGSTOP) continue;
    const int was = sigismember(&before.sa_mask, candidate);
    const int now = sigismember(&after.sa_mask, candidate);
    if (was >= 0 && now >= 0) check(was == now, "restored signal mask exactly");
  }
}

PriorAction take_prior_actions() {
  PriorAction prior{};
  check(sigaction(SIGSEGV, nullptr, &prior.segv) == 0,
        "query initial SIGSEGV owner");
  check(sigaction(SIGILL, nullptr, &prior.ill) == 0,
        "query initial SIGILL owner");
  require_default(prior.segv, "SIGSEGV must be unowned at fixture startup");
  require_default(prior.ill, "SIGILL must be unowned at fixture startup");
  return prior;
}

void install_exclusive_transport() {
  check(lsc_install() == 0, "install exclusive fixture signal owner");
  check(lsc_attach() == 0, "attach guarded alternate signal stack");
}

void remove_exclusive_transport() {
  check(lsc_detach() == 0, "detach signal stack after accesses stop");
  check(lsc_uninstall() == 0, "remove exclusive signal owner before SDK destruction");
}

bool admitted_fault(const CallbackState& state, uintptr_t expected,
                    lsc_operation operation, lsc_fault& fault) {
  return lsc_last_fault(&fault) && fault.signal_number == SIGSEGV &&
         fault.signal_code == SEGV_ACCERR && fault.address == expected &&
         fault.instruction == (operation == LSC_READ
                                   ? reinterpret_cast<uintptr_t>(lsc_read_site)
                                   : reinterpret_cast<uintptr_t>(lsc_write_site)) &&
         fault.operation == operation && fault.on_altstack != 0 &&
         fault.count > 0 && expected >= reinterpret_cast<uintptr_t>(state.base) &&
         expected - reinterpret_cast<uintptr_t>(state.base) <=
             state.size - sizeof(uint32_t);
}
#endif

struct Fixture final {
  explicit Fixture(size_t system_page)
      : page(system_page), mapping(16 * system_page), memory(), heap() {
    check(page >= 4096 && (page & (page - 1)) == 0,
          "supported SDK system page size");
    check(mapping.size() <= UINT32_MAX, "fixture guest addresses fit 32 bits");
    heap.Initialize(&memory, mapping.base(), rex::memory::HeapType::kGuestPhysical,
                    0, static_cast<uint32_t>(mapping.size()),
                    static_cast<uint32_t>(page), nullptr);
    check(heap.BaseHeap::AllocFixed(
              0, static_cast<uint32_t>(mapping.size()), static_cast<uint32_t>(page),
              rex::memory::kMemoryAllocationReserve | rex::memory::kMemoryAllocationCommit,
              rex::memory::kMemoryProtectRead | rex::memory::kMemoryProtectWrite),
          "SDK physical page metadata allocation");
    std::fill(mapping.base(), mapping.base() + mapping.size(), 0xa5);
    state = std::make_unique<CallbackState>(CallbackState{
        memory, heap, mapping.base(), mapping.size(), page});
    state->watched_ea = static_cast<uint32_t>(2 * page);
    state->mmio_guest_ea = static_cast<uint32_t>(3 * page);
    invalidation_handle = memory.RegisterPhysicalMemoryInvalidationCallback(
        invalidation_callback, state.get());
    check(invalidation_handle != nullptr,
          "real Memory invalidation callback registration");
  }

  ~Fixture() {
    if (handler) {
      // Every native owner has already been removed; the SDK table is empty.
      handler.reset();
    }
    if (invalidation_handle) {
      memory.UnregisterPhysicalMemoryInvalidationCallback(invalidation_handle);
      invalidation_handle = nullptr;
    }
  }

  void install_sdk_handler() {
#ifndef LSC_ORDINARY_ONLY
    prior = take_prior_actions();
#endif
    handler = Handler::Install(mapping.base(), mapping.base() + mapping.size(),
                               mapping.base() + mapping.size(), host_to_guest,
                               state.get(), access_violation, state.get());
    check(handler != nullptr && Handler::global_handler() == handler.get(),
          "real SDK MMIOHandler installation and singleton");
    check(handler->RegisterRange(kMmioAddress, 0xffffffffu, 1, state.get(),
                                 mmio_read, mmio_write),
          "real SDK MMIO range registration");
    check(handler->RegisterRange(state->mmio_guest_ea, 0xffffffffu, 1,
                                 state.get(), mmio_read, mmio_write),
          "real in-arena MMIO range registration for bridge ordering");
  }

  void handoff_from_sdk() {
    // Uninstall this exact SDK callback but retain the object and its callback
    // storage. This is process-exclusive, before any worker is created.
    rex::arch::ExceptionHandler::Uninstall(MMIOAccess::exception_thunk(),
                                           handler.get());
#ifndef LSC_ORDINARY_ONLY
    verify_restored_action(SIGSEGV, prior.segv,
                           "SDK handoff restores SIGSEGV owner");
    verify_restored_action(SIGILL, prior.ill,
                           "SDK handoff restores SIGILL owner");
#endif
  }

  bool trigger_watch(uint32_t guest_ea) {
    const uintptr_t host = reinterpret_cast<uintptr_t>(mapping.base()) + guest_ea;
    bool handled = false;
    dispatch_sdk_access(*handler, host, Operation::kWrite, handled);
    return handled;
  }

  bool query_protection(uint32_t guest_ea, PageAccess expected) {
    size_t length = page;
    PageAccess actual = PageAccess::kNoAccess;
    const bool queried = rex::memory::QueryProtect(mapping.base() + guest_ea,
                                                    length, actual);
    return queried && length >= page && actual == expected;
  }

  size_t page;
  Mapping mapping;
  Memory memory;
  PhysicalHeap heap;
  std::unique_ptr<CallbackState> state;
  std::unique_ptr<Handler> handler;
  void* invalidation_handle = nullptr;
#ifndef LSC_ORDINARY_ONLY
  PriorAction prior{};
#endif
};

void test_mmio(Fixture& fixture) {
  uint32_t value = 0xfeedfaceu;
  const unsigned watches_before = fixture.state->invalidations;
  check(fixture.handler->CheckLoad(kMmioAddress, &value) && value == kMmioValue,
        "real direct SDK CheckLoad consumes once");
  check(fixture.state->mmio_reads == 1 &&
            fixture.state->invalidations == watches_before &&
            fixture.state->guest_dispatches == 0,
        "MMIO read never reaches watch or guest dispatch");
  check(fixture.handler->CheckStore(kMmioAddress, 0x10203040u),
        "real direct SDK CheckStore consumes once");
  check(fixture.state->mmio_writes == 1 &&
            fixture.state->last_mmio_store == 0x10203040u &&
            fixture.state->invalidations == watches_before &&
            fixture.state->guest_dispatches == 0,
        "MMIO store has no duplicate watch or guest effect");
  value = 0xfeedfaceu;
  check(!fixture.handler->CheckLoad(0x1000, &value) && value == 0xfeedfaceu &&
            !fixture.handler->CheckStore(0x1000, 1) &&
            fixture.state->mmio_reads == 1 && fixture.state->mmio_writes == 1,
        "unmapped MMIO declines without callbacks or output writes");
}

std::array<lgi::Consumer, 1> sdk_ordered_consumers(Fixture& fixture) {
  return {{[&fixture](const lgi::AccessRequest& request, uintptr_t) {
    uint32_t value = 0;
    if (fixture.handler->CheckLoad(request.effective_address, &value))
      return lgi::ConsumerResult::Mmio(value);
    return lgi::ConsumerResult::Pass();
  }}};
}

void test_mmio_in_checked_path(Fixture& fixture) {
  auto& state = *fixture.state;
  const auto bytes = std::span<uint8_t>(fixture.mapping.base(),
                                        fixture.mapping.size());
  lgi::GuestArena arena{std::span<uint8_t>(fixture.mapping.base(), fixture.mapping.size()),
                       0, static_cast<uint32_t>(fixture.mapping.size()),
                       true, fixture.page, 0x1000u};
  unsigned backend_calls = 0;
  const auto consumers = sdk_ordered_consumers(fixture);
  const lgi::Backend backend = [&](const void*) {
    ++backend_calls;
    return lgi::BackendResult::Reject();
  };
  uint32_t output = 0xfeedfaceu;
  const unsigned reads_before = state.mmio_reads;
  const unsigned watches_before = state.invalidations;
  const auto result = lgi::checked_load32(
      arena, {state.mmio_guest_ea, kGuestPc, 4, lgi::Operation::read},
      static_cast<uint32_t>(fixture.mapping.size() - fixture.page),
      consumers, backend, output);
  check(result == lgi::AccessStatus::mmio_consumed && output == kMmioValue &&
            backend_calls == 0 && state.mmio_reads == reads_before + 1 &&
            state.invalidations == watches_before && state.guest_dispatches == 0,
        "real MMIO callback consumes checked access before load/watch/guest dispatch");
  check(bytes[state.mmio_guest_ea] == 0xa5,
        "MMIO checked-path consumption does not read or alter RAM backing");
}

void test_watch_component(Fixture& fixture) {
  auto& state = *fixture.state;
  const uint32_t ea = state.watched_ea;
  const uintptr_t host = reinterpret_cast<uintptr_t>(fixture.mapping.base()) + ea;
  fixture.heap.EnableAccessCallbacks(ea, static_cast<uint32_t>(fixture.page),
                                     true, false);
  check(fixture.query_protection(ea, PageAccess::kReadOnly),
        "real PhysicalHeap watch establishes read-only host protection");
  const unsigned invalidations_before = state.invalidations;
  bool handled = false;
  dispatch_sdk_access(*fixture.handler, host, Operation::kWrite, handled);
  check(handled && state.invalidations == invalidations_before + 1,
        "real SDK exception callback consumes write watch");
  check(fixture.query_protection(ea, PageAccess::kReadWrite),
        "real PhysicalHeap callback repairs write protection");
  dispatch_sdk_access(*fixture.handler, host, Operation::kWrite, handled);
  check(handled && state.invalidations == invalidations_before + 1,
        "already-repaired page consumes without duplicate invalidation");
  check(state.recursive_rejected,
        "nested test callback is rejected before redispatch");
}

#ifndef LSC_ORDINARY_ONLY
void test_guest_delivery(Fixture& fixture) {
  auto& state = *fixture.state;
  auto bytes = std::span<uint8_t>(fixture.mapping.base(), fixture.mapping.size());
  const uint32_t read_ea = 0;
  const uint32_t page = static_cast<uint32_t>(fixture.page);
  const uint32_t live_sp = static_cast<uint32_t>(fixture.mapping.size() - page);
  const uint32_t owner_sp = static_cast<uint32_t>(fixture.mapping.size() - 0x100u);
  check(fixture.heap.BaseHeap::Protect(read_ea, page,
                             rex::memory::kMemoryProtectNoAccess),
        "SDK page metadata and host access become no-access");
  check(fixture.query_protection(read_ea, PageAccess::kNoAccess),
        "real SDK no-access page confirmed before checked load");

  lgi::GuestArena arena{bytes, 8 * page, static_cast<uint32_t>(bytes.size()),
                       true, fixture.page,
                       reinterpret_cast<uintptr_t>(lsc_read_site)};
  const auto consumers = sdk_ordered_consumers(fixture);
  auto backend = [&](const void* address) {
    uint32_t raw = 0xfeedfaceu;
    const auto status = lsc_read32(fixture.mapping.base(), fixture.mapping.size(),
                                   address, &raw);
    if (status == LSC_OK) return lgi::BackendResult::Success(raw);
    lsc_fault fault{};
    const bool admitted = status == LSC_FAULT &&
        admitted_fault(state, reinterpret_cast<uintptr_t>(address), LSC_READ, fault);
    check(raw == 0xfeedfaceu,
          "captured guest fault leaves read result untouched");
    if (!admitted) return lgi::BackendResult::Reject();
    // The SDK consumer runs only after lsc_read32 returned through sigreturn.
    bool consumed = false;
    try {
      dispatch_sdk_access(*fixture.handler, fault.address, Operation::kRead,
                          consumed);
    } catch (...) {
      lsc_terminal();
    }
    if (consumed) {
      // A concurrent repair may make the SDK callback consume without invoking
      // the watcher. Try this exact helper once; never re-enter a repair loop.
      uint32_t retry_raw = 0xfeedfaceu;
      if (lsc_read32(fixture.mapping.base(), fixture.mapping.size(),
                     address, &retry_raw) == LSC_OK)
        return lgi::BackendResult::Success(retry_raw);
      lsc_terminal();
    }
    ++state.guest_dispatches;
    return lgi::BackendResult::Fault(fault.address, fault.instruction, true);
  };

  for (const int disposition : {-1, 1}) {
    check(fixture.heap.BaseHeap::Protect(read_ea, page,
                               rex::memory::kMemoryProtectNoAccess),
          "guest fault page re-protected before each delivery case");
    check(fixture.query_protection(read_ea, PageAccess::kNoAccess),
          "guest fault page protection rechecked before each delivery case");
    PPCContext guest{};
    guest.r1.u64 = owner_sp;
    guest.r14.u64 = 14;
    guest.fpscr.InitHost();
    unsigned filters = 0, cleanups = 0;
    std::vector<pgeh::Scope> scopes;
    scopes.push_back({kGuestPc, kGuestPc + 4, 0, {},
                      [&](auto&, uint32_t) { ++cleanups; }});
    scopes.push_back({kGuestPc, kGuestPc + 4, kGuestLabel,
        lgi::wrap_filter([&](PPCContext& visible, const auto&, uint32_t establisher) {
          ++filters;
          const uint32_t scratch = lgi::scratch_sp(live_sp);
          check(visible.r1.u32 == scratch && visible.r3.u32 == scratch + 0x70 &&
                    visible.r4.u32 == owner_sp && visible.r12.u32 == owner_sp &&
                    establisher == owner_sp && visible.r14.u64 == 14,
                "record filter receives M4 owner and scratch arguments");
          const auto be = [&](uint32_t offset) {
            check(uint64_t(offset) + 4 <= bytes.size(),
                  "guest record pointer remains in mapped backing");
            return (uint32_t(bytes[offset]) << 24) |
                   (uint32_t(bytes[offset + 1]) << 16) |
                   (uint32_t(bytes[offset + 2]) << 8) | bytes[offset + 3];
          };
          const uint32_t record = be(visible.r3.u32);
          check(bytes[scratch + 0x6f] == 0xa5 &&
                    bytes[scratch + 0x78] == 0xa5 &&
                    bytes[scratch + 0xd0] == 0xa5,
                "M4 serialization preserves scratch canaries");
          check(record == scratch + 0x80 && be(visible.r3.u32 + 4) == 0 &&
                    be(record) == lgi::kGuestAccessViolation &&
                    be(record + 4) == 0 && be(record + 8) == 0 &&
                    be(record + 12) == kGuestPc && be(record + 16) == 2 &&
                    be(record + 20) == 0 && be(record + 24) == read_ea,
                "real fault metadata serialized into the M4 guest record");
          for (uint32_t offset = 28; offset < 80; offset += 4)
            check(be(record + offset) == 0, "unused M4 record fields remain zero");
          if (disposition < 0) {
            visible.r14.u64 = 99;
            check(fixture.heap.BaseHeap::Protect(read_ea, page,
                         rex::memory::kMemoryProtectRead |
                         rex::memory::kMemoryProtectWrite),
                  "negative filter explicitly repairs SDK metadata/protection");
          }
          return disposition;
        }), {}});
    pgeh::Owner owner(guest, std::move(scopes));
    owner.declare_label(kGuestLabel);
    const auto selected = pgeh::region(owner, [&] {
      owner.set_pc(kGuestPc);
      owner.before_call();
      guest.r1.u64 = live_sp;
      guest.r14.u64 = 42;
      uint32_t output = 0xdecafbad;
      const auto result = lgi::checked_load32(
          arena, {read_ea, kGuestPc, 4, lgi::Operation::read}, live_sp,
          consumers, backend, output);
      if (disposition < 0) {
        check(result == lgi::AccessStatus::guest_fault && output == 0xdecafbadu &&
                  cleanups == 0 && guest.r1.u32 == live_sp && guest.r14.u64 == 42,
              "negative disposition returns live without cleanup");
        const auto retry = lgi::checked_load32(
            arena, {read_ea, kGuestPc, 4, lgi::Operation::read}, live_sp,
            consumers, backend, output);
        check(retry == lgi::AccessStatus::success && output == 0xa5a5a5a5u,
              "fresh checked read succeeds after explicit negative repair");
      }
    });
    check(filters == 1 &&
              selected == (disposition < 0 ? 0 : kGuestLabel) &&
              cleanups == (disposition < 0 ? 0u : 1u),
          "negative continuation and accepted owner cleanup preserved");
    check(!lgi::current_delivery && !lgi::access_dispatch_active,
          "guest delivery guards clear after filter transfer");
  }
}

uint32_t host_word(uintptr_t address) {
  uint32_t value;
  std::memcpy(&value, reinterpret_cast<const void*>(address), sizeof(value));
  return value;
}

void test_native_write_watch(Fixture& fixture) {
  auto& state = *fixture.state;
  const uint32_t ea = state.watched_ea;
  const uintptr_t host = reinterpret_cast<uintptr_t>(fixture.mapping.base()) + ea;
  const unsigned first_callback = state.invalidations;
  const unsigned guest_before = state.guest_dispatches;
  const unsigned mmio_writes_before = state.mmio_writes;
  fixture.heap.EnableAccessCallbacks(ea, static_cast<uint32_t>(fixture.page),
                                     true, false);
  check(fixture.query_protection(ea, PageAccess::kReadOnly),
        "real write watch protects page before exact store");
  check(!fixture.handler->CheckStore(ea, 0x01020304u) &&
            state.mmio_writes == mmio_writes_before &&
            state.invalidations == first_callback,
        "real MMIO consumer declines before the protected watch store");
  const uint32_t before = host_word(host);
  enum lsc_status status = lsc_write32(fixture.mapping.base(),
                                       fixture.mapping.size(),
                                       fixture.mapping.base() + ea, 0x01020304u);
  check(status == LSC_FAULT, "exact protected store captured and returned");
  lsc_fault fault{};
  check(admitted_fault(state, host, LSC_WRITE, fault),
        "write-watch fault has exact site/address/operation metadata");
  const uint32_t after_failed = host_word(host);
  check(after_failed == before, "faulting store has no duplicate memory effect");
  bool consumed = false;
  dispatch_sdk_access(*fixture.handler, fault.address, Operation::kWrite, consumed);
  check(consumed && state.invalidations == first_callback + 1,
        "real SDK callback and PhysicalHeap invalidator consume captured write");
  check(fixture.query_protection(ea, PageAccess::kReadWrite),
        "real watch repair restores write access");
  check(lsc_write32(fixture.mapping.base(), fixture.mapping.size(),
                    fixture.mapping.base() + ea, 0x01020304u) == LSC_OK,
        "one fresh store succeeds after actual SDK repair");
  check(host_word(host) == 0x01020304u,
        "fresh store commits exactly once");
  check(lsc_write32(fixture.mapping.base(), fixture.mapping.size(),
                    fixture.mapping.base() + ea, 0x11223344u) == LSC_OK &&
        host_word(host) == 0x11223344u && state.invalidations == first_callback + 1,
        "repeated unprotected store succeeds with no duplicate invalidation");
  dispatch_sdk_access(*fixture.handler, host, Operation::kWrite, consumed);
  check(consumed && state.invalidations == first_callback + 1,
        "repeated SDK dispatch after repair has no duplicate invalidation");

  // Re-arm the same page and prove another, distinct write is serviced once.
  fixture.heap.EnableAccessCallbacks(ea, static_cast<uint32_t>(fixture.page),
                                     true, false);
  check(fixture.query_protection(ea, PageAccess::kReadOnly),
        "watch can be explicitly re-armed");
  status = lsc_write32(fixture.mapping.base(), fixture.mapping.size(),
                       fixture.mapping.base() + ea, 0x55667788u);
  check(status == LSC_FAULT, "re-armed write watch captures second store");
  check(host_word(host) == 0x11223344u, "re-armed failed store commits no bytes");
  check(admitted_fault(state, host, LSC_WRITE, fault),
        "second store has exact site/address/operation metadata");
  const unsigned before_second = state.invalidations;
  dispatch_sdk_access(*fixture.handler, fault.address, Operation::kWrite, consumed);
  check(consumed && state.invalidations == before_second + 1,
        "second watch invokes one invalidation callback");
  check(fixture.query_protection(ea, PageAccess::kReadWrite),
        "second real watch repair restores page");
  check(lsc_write32(fixture.mapping.base(), fixture.mapping.size(),
                    fixture.mapping.base() + ea, 0x55667788u) == LSC_OK &&
            host_word(host) == 0x55667788u,
        "second explicit fresh store succeeds once");
  check(state.guest_dispatches == guest_before, "consumed write watches never reach guest delivery");
}

#ifndef LSC_TERMINAL_DIAGNOSTICS
void test_terminal_mode(Fixture& fixture, const char* mode) {
  auto& state = *fixture.state;
  if (std::string_view(mode) == "callback-failure") {
    state.fail_next_invalidation = true;
    const uintptr_t host = reinterpret_cast<uintptr_t>(fixture.mapping.base()) + state.watched_ea;
    fixture.heap.EnableAccessCallbacks(state.watched_ea,
        static_cast<uint32_t>(fixture.page), true, false);
    check(lsc_write32(fixture.mapping.base(), fixture.mapping.size(),
                      fixture.mapping.base() + state.watched_ea, 7) == LSC_FAULT,
          "callback failure case reaches an exact protected store");
    lsc_fault fault{};
    check(admitted_fault(state, host, LSC_WRITE, fault),
          "callback failure store metadata is admitted");
    bool handled = false;
    try {
      dispatch_sdk_access(*fixture.handler, host, Operation::kWrite, handled);
    } catch (...) {
      lsc_terminal();
    }
    check(false, "throwing SDK callback unexpectedly returned");
  }
  if (std::string_view(mode) == "repair-failure") {
    state.decline_write_repair = true;
    const uintptr_t host = reinterpret_cast<uintptr_t>(fixture.mapping.base()) +
                          state.watched_ea;
    fixture.heap.EnableAccessCallbacks(state.watched_ea,
        static_cast<uint32_t>(fixture.page), true, false);
    check(lsc_write32(fixture.mapping.base(), fixture.mapping.size(),
                      fixture.mapping.base() + state.watched_ea, 7) == LSC_FAULT,
          "repair failure case reaches an exact protected store");
    lsc_fault fault{};
    check(admitted_fault(state, host, LSC_WRITE, fault),
          "repair failure store has exact admitted provenance");
    bool handled = false;
    dispatch_sdk_access(*fixture.handler, fault.address, Operation::kWrite, handled);
    check(handled && fixture.query_protection(state.watched_ea,
                                             PageAccess::kReadOnly),
          "injected false repair is exposed before retry");
    if (lsc_write32(fixture.mapping.base(), fixture.mapping.size(),
                    fixture.mapping.base() + state.watched_ea, 7) != LSC_FAULT)
      check(false, "unrepaired second exact store did not fault");
    lsc_terminal();
  }
  if (std::string_view(mode) == "unhandled") {
    const uint32_t page = static_cast<uint32_t>(fixture.page);
    const uint32_t live_sp = static_cast<uint32_t>(fixture.mapping.size() - page);
    const uintptr_t host = reinterpret_cast<uintptr_t>(fixture.mapping.base());
    check(fixture.heap.BaseHeap::Protect(0, page, rex::memory::kMemoryProtectNoAccess),
          "unhandled guest page starts inaccessible");
    auto bytes = std::span<uint8_t>(fixture.mapping.base(), fixture.mapping.size());
    lgi::GuestArena arena{bytes, 8 * page, static_cast<uint32_t>(bytes.size()),
                         true, fixture.page,
                         reinterpret_cast<uintptr_t>(lsc_read_site)};
    const auto consumers = sdk_ordered_consumers(fixture);
    PPCContext guest{};
    guest.r1.u64 = fixture.mapping.size() - 0x100u;
    guest.fpscr.InitHost();
    std::vector<pgeh::Scope> scopes;
    scopes.push_back({kGuestPc, kGuestPc + 4, kGuestLabel,
        lgi::wrap_filter([](PPCContext&, const auto&, uint32_t) { return 0; }), {}});
    pgeh::Owner owner(guest, std::move(scopes));
    owner.declare_label(kGuestLabel);
    const uint32_t selected = pgeh::region(owner, [&] {
      owner.set_pc(kGuestPc);
      owner.before_call();
      guest.r1.u64 = live_sp;
      const auto backend = [&](const void* address) {
        uint32_t raw = 0;
        const auto status = lsc_read32(fixture.mapping.base(), fixture.mapping.size(),
                                       address, &raw);
        lsc_fault fault{};
        if (status != LSC_FAULT ||
            !admitted_fault(state, host, LSC_READ, fault))
          return lgi::BackendResult::Reject();
        bool consumed = false;
        try {
          dispatch_sdk_access(*fixture.handler, fault.address, Operation::kRead,
                              consumed);
        } catch (...) {
          lsc_terminal();
        }
        if (consumed) {
          uint32_t retry_raw = 0xfeedfaceu;
          if (lsc_read32(fixture.mapping.base(), fixture.mapping.size(),
                         address, &retry_raw) == LSC_OK)
            return lgi::BackendResult::Success(retry_raw);
          lsc_terminal();
        }
        ++state.guest_dispatches;
        return lgi::BackendResult::Fault(fault.address, fault.instruction, true);
      };
      try {
        uint32_t output = 0;
        (void)lgi::checked_load32(arena,
            {0, kGuestPc, 4, lgi::Operation::read}, live_sp,
            consumers, backend, output);
      } catch (const pgeh::Unhandled&) {
        lsc_terminal();
      }
      check(false, "unhandled guest fault returned from record dispatch");
    });
    (void)selected;
    check(false, "unhandled owner unexpectedly returned or accepted");
  }
}
#else
#include "terminal_modes.inl"
#endif
#endif
void measure_components(Fixture& fixture) {
  // Include the fixture's callback validation/counters; no overhead subtraction.
  using Clock = std::chrono::steady_clock;
  constexpr unsigned mmio_repetitions = 100000, watch_repetitions = 1000;
  uint32_t value = 0;
  auto start = Clock::now();
  for (unsigned i = 0; i < mmio_repetitions; ++i)
    check(fixture.handler->CheckLoad(kMmioAddress, &value) && value == kMmioValue,
          "benchmark direct MMIO");
  const double mmio_ns = std::chrono::duration<double, std::nano>(Clock::now() - start).count()
      / mmio_repetitions;
  const unsigned before = fixture.state->invalidations;
  start = Clock::now();
  for (unsigned i = 0; i < watch_repetitions; ++i) {
    fixture.heap.EnableAccessCallbacks(fixture.state->watched_ea,
        static_cast<uint32_t>(fixture.page), true, false);
    check(fixture.trigger_watch(fixture.state->watched_ea), "benchmark watch repair");
  }
  const double watch_ns = std::chrono::duration<double, std::nano>(Clock::now() - start).count()
      / watch_repetitions;
  check(fixture.state->invalidations == before + watch_repetitions &&
        fixture.query_protection(fixture.state->watched_ea, PageAccess::kReadWrite),
        "benchmark watch callbacks and final repair");
  std::printf("SDK_COMPONENT_BENCH ns_per_operation direct_mmio=%.3f n=%u "
              "watch_enable_dispatch_repair=%.3f n=%u\n",
              mmio_ns, mmio_repetitions, watch_ns, watch_repetitions);
}
}  // namespace

int main(int argc, char** argv) {
  const char* mode = argc > 1 ? argv[1] : "normal";
  check(argc <= 2, "one optional fixture mode is supported");
#ifndef LSC_ORDINARY_ONLY
  const rlimit no_core{0, 0};
  check(setrlimit(RLIMIT_CORE, &no_core) == 0,
        "disable child core dumps for fault cases");
#endif
  const size_t page = rex::memory::page_size();
  Fixture fixture(page);
  fixture.install_sdk_handler();
  test_mmio(fixture);
  fixture.state->recursive_test = true;
  test_watch_component(fixture);
  fixture.state->recursive_test = false;
  fixture.handoff_from_sdk();
  test_mmio_in_checked_path(fixture);

#ifdef LSC_ORDINARY_ONLY
  check(std::string_view(mode) == "normal" || std::string_view(mode) == "benchmark",
        "ordinary-only fixture supports normal/benchmark modes only");
#else
  check(std::string_view(mode) == "normal" ||
            std::string_view(mode) == "benchmark" ||
            std::string_view(mode) == "callback-failure" ||
            std::string_view(mode) == "repair-failure" ||
            std::string_view(mode) == "unhandled",
        "unsupported native fixture mode");
  install_exclusive_transport();
  if (std::string_view(mode) == "callback-failure" ||
      std::string_view(mode) == "repair-failure" ||
      std::string_view(mode) == "unhandled")
    test_terminal_mode(fixture, mode);
  test_guest_delivery(fixture);
  test_native_write_watch(fixture);
  remove_exclusive_transport();
#endif
  if (std::string_view(mode) == "benchmark") measure_components(fixture);
  fixture.handler.reset();
  fixture.memory.UnregisterPhysicalMemoryInvalidationCallback(
      fixture.invalidation_handle);
  fixture.invalidation_handle = nullptr;
  check(Handler::global_handler() == nullptr,
        "SDK singleton and callbacks removed before mapping destruction");
  std::printf("SDK_COMPOSITION PASS checks=%u mode=%s\n", checks, mode);
  return 0;
}
