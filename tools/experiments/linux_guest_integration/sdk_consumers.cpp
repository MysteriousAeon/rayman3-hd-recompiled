// Ordinary-code SDK consumer composition experiment; SDK owns any OS handler.
#include <rex/exception_handler.h>
#include <rex/memory/utils.h>
#include <rex/system/mmio_handler.h>
#include "record_bridge.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <utility>

namespace {
using Exception = rex::arch::Exception;
using Operation = Exception::AccessViolationOperation;
using PageAccess = rex::memory::PageAccess;
constexpr uint32_t kMmioAddress = 0x7f000000u;
constexpr uint32_t kMmioValue = 0x1234abcdu;
constexpr uintptr_t kGuestSite = 0x12345000u;  // Provenance marker, never executed.
unsigned checks = 0;

void check(bool condition, const char* message) {
  ++checks;
  if (!condition) {
    std::fprintf(stderr, "SDK_CONSUMERS FAIL: %s\n", message);
    std::exit(2);
  }
}

struct Mapping {
  size_t page = rex::memory::page_size();
  uint8_t* base = nullptr;
  Mapping() {
    check(page >= 4096 && page <= UINT32_MAX / 3, "supported host page size");
    base = static_cast<uint8_t*>(rex::memory::AllocFixed(
        nullptr, 3 * page, rex::memory::AllocationType::kReserveCommit, PageAccess::kReadWrite));
    check(base != nullptr, "synthetic page allocation");
  }
  ~Mapping() {
    // The SDK POSIX implementation passes length to munmap; Windows release
    // uses VirtualFree's required zero length despite the shared header wording.
#if REX_PLATFORM_WIN32
    constexpr size_t release_length = 0;
#else
    const size_t release_length = 3 * page;
#endif
    if (base && !rex::memory::DeallocFixed(base, release_length,
                                          rex::memory::DeallocationType::kRelease))
      std::abort();
  }
  void protect(size_t index, PageAccess expected) {
    check(rex::memory::Protect(base + index * page, page, expected), "SDK Protect");
    size_t length = page;
    PageAccess actual = PageAccess::kReadWrite;
    check(rex::memory::QueryProtect(base + index * page, length, actual) &&
              length >= page && actual == expected,
          "SDK QueryProtect confirms live mapping before callback");
  }
};

struct State;
uint32_t host_to_guest(const void* context, const void* address);
bool watch_callback(std::unique_lock<std::recursive_mutex> lock, void* context,
                    void* address, bool is_write);

class CallbackAccess : public rex::runtime::MMIOHandler {
 public:
  static auto callback() {
    // The inherited function's pointer-to-member retains its base class type.
    // Access is granted here; invocation on the real installed base is valid.
    return &CallbackAccess::ExceptionCallback;
  }
};

enum class Stage { pre_access, post_fault };
enum class Result { proceed, mmio, watch, guest_fault, rejected, recursive };
struct State {
  Mapping& mapping;
  rex::runtime::MMIOHandler* handler = nullptr;
  unsigned reads = 0, writes = 0, watches = 0, guest_dispatches = 0;
  uint32_t last_store = 0;
  bool watch_consume = false;
  bool test_recursion = false;
  bool recursive_rejected = false;
  bool dispatch_active = false;
  std::function<void(uint32_t)> on_guest_fault{};

  Result dispatch(Stage stage, uint32_t ea, uintptr_t address, uintptr_t instruction,
                  Operation operation, uint32_t& value) {
    if (dispatch_active) return Result::recursive;
    struct Guard {
      bool& active;
      explicit Guard(bool& flag) : active(flag) { active = true; }
      ~Guard() { active = false; }
    } guard(dispatch_active);
    if (operation != Operation::kRead && operation != Operation::kWrite)
      return Result::rejected;
    if (stage == Stage::pre_access) {
      if (operation != Operation::kRead) return Result::rejected;
      return handler->CheckLoad(ea, &value) ? Result::mmio : Result::proceed;
    }
    rex::arch::HostThreadContext context{};
    Exception exception{};
    exception.InitializeAccessViolation(&context, address, operation);
    if ((handler->*CallbackAccess::callback())(&exception)) return Result::watch;
    // Tight experimental policy, not the SDK's default terminal fallback.
    const uintptr_t base = reinterpret_cast<uintptr_t>(mapping.base);
    if (operation != Operation::kRead || instruction != kGuestSite || address < base ||
        address - base >= 3 * mapping.page || 3 * mapping.page - (address - base) < 4 ||
        ea != address - base || (ea & 3u) != 0)
      return Result::rejected;
    ++guest_dispatches;
    if (on_guest_fault) on_guest_fault(ea);
    return Result::guest_fault;
  }
};

uint32_t host_to_guest(const void* context, const void* address) {
  const auto& mapping = *static_cast<const Mapping*>(context);
  return static_cast<uint32_t>(reinterpret_cast<uintptr_t>(address) -
                               reinterpret_cast<uintptr_t>(mapping.base));
}
uint32_t mmio_read(void*, void* context, uint32_t address) {
  auto& state = *static_cast<State*>(context);
  check(address == kMmioAddress, "MMIO read address");
  ++state.reads;
  return kMmioValue;
}
void mmio_write(void*, void* context, uint32_t address, uint32_t value) {
  auto& state = *static_cast<State*>(context);
  check(address == kMmioAddress, "MMIO store address");
  ++state.writes;
  state.last_store = value;
}
bool watch_callback(std::unique_lock<std::recursive_mutex> lock, void* context,
                    void* address, bool is_write) {
  auto& state = *static_cast<State*>(context);
  check(lock.owns_lock(), "real SDK callback supplies locked critical region");
  check(address == state.mapping.base + state.mapping.page, "watch callback address");
  ++state.watches;
  if (state.test_recursion) {
    uint32_t value = 0;
    state.recursive_rejected = state.dispatch(Stage::post_fault, 0, reinterpret_cast<uintptr_t>(address),
                                              kGuestSite, Operation::kRead, value) == Result::recursive;
  }
  if (state.watch_consume) {
    check(is_write, "synthetic write-watch operation");
    check(rex::memory::Protect(address, state.mapping.page, PageAccess::kReadWrite),
          "synthetic watcher repairs page using SDK Protect");
  }
  return state.watch_consume;
}
}  // namespace

int main() {
  Mapping mapping;
  State state{mapping};
  {
    check(rex::runtime::MMIOHandler::global_handler() == nullptr, "no existing MMIO singleton");
    auto handler = rex::runtime::MMIOHandler::Install(
        mapping.base, mapping.base, mapping.base + 3 * mapping.page - 1,
        host_to_guest, &mapping, watch_callback, &state);
    check(handler != nullptr, "SDK MMIO installation");
    state.handler = handler.get();
    check(handler->RegisterRange(kMmioAddress, 0xfffffff0u, 16, &state,
                                 mmio_read, mmio_write), "SDK register MMIO range");
    uint32_t value = 0xfeedfaceu;
    check(state.dispatch(Stage::pre_access, kMmioAddress, 0, 0, Operation::kRead, value) == Result::mmio &&
              value == kMmioValue && state.reads == 1 && state.watches == 0 &&
              state.guest_dispatches == 0, "real CheckLoad consumes first once");
    check(handler->CheckStore(kMmioAddress, 0x10203040u) && state.writes == 1 &&
              state.last_store == 0x10203040u, "real CheckStore invokes one callback");
    value = 0xfeedfaceu;
    check(!handler->CheckLoad(0x1000, &value) && value == 0xfeedfaceu &&
              !handler->CheckStore(0x1000, 1) && state.writes == 1,
          "unmapped MMIO has no callback or output effect");
    check(state.dispatch(Stage::pre_access, 0x1000, 0, 0, Operation::kRead, value) == Result::proceed &&
              state.reads == 1 && state.watches == 0 && state.guest_dispatches == 0,
          "unconsumed pre-access request proceeds without synthetic fault dispatch");

    mapping.protect(1, PageAccess::kReadOnly);
    state.watch_consume = true;
    state.test_recursion = true;
    const uintptr_t page_address = reinterpret_cast<uintptr_t>(mapping.base + mapping.page);
    value = 0xfeedfaceu;
    check(state.dispatch(Stage::post_fault, static_cast<uint32_t>(mapping.page), page_address, kGuestSite,
                         Operation::kWrite, value) == Result::watch &&
              state.watches == 1 && state.recursive_rejected && state.guest_dispatches == 0 &&
              value == 0xfeedfaceu, "real protected-page callback consumes before guest");
    size_t repaired_length = mapping.page;
    PageAccess repaired_access = PageAccess::kNoAccess;
    check(rex::memory::QueryProtect(mapping.base + mapping.page, repaired_length, repaired_access) &&
              repaired_length >= mapping.page && repaired_access == PageAccess::kReadWrite,
          "synthetic watch repaired page protection exactly once");
    check(state.dispatch(Stage::post_fault, static_cast<uint32_t>(mapping.page), page_address, kGuestSite,
                         Operation::kWrite, value) == Result::watch &&
              state.watches == 1 && state.guest_dispatches == 0,
          "already-cleared protection consumes without duplicate watch callback");

    state.watch_consume = false;
    state.test_recursion = false;
    mapping.protect(1, PageAccess::kNoAccess);
    {
      constexpr uint32_t guest_pc = 0x82001234, guest_label = 0x82001300;
      const uint32_t live_sp = static_cast<uint32_t>(3 * mapping.page - 0x100);
      PPCContext guest{}; guest.r1.u64 = 3 * mapping.page; guest.fpscr.InitHost();
      lgi::GuestArena arena{std::span<uint8_t>(mapping.base, 3 * mapping.page),
          static_cast<uint32_t>(2 * mapping.page), static_cast<uint32_t>(3 * mapping.page),
          true, mapping.page, kGuestSite};
      unsigned filters = 0, cleanups = 0;
      std::vector<pgeh::Scope> scopes;
      scopes.push_back({guest_pc, guest_pc + 4, 0, {}, [&](auto&, uint32_t) { ++cleanups; }});
      scopes.push_back({guest_pc, guest_pc + 4, guest_label,
          lgi::wrap_filter([&](PPCContext& visible, const auto&, uint32_t establisher) {
            ++filters;
            const auto be = [&](uint32_t offset) {
              check(uint64_t(offset) + 4 <= arena.bytes.size(), "composed guest pointer bounded");
              return (uint32_t(arena.bytes[offset]) << 24) | (uint32_t(arena.bytes[offset + 1]) << 16) |
                     (uint32_t(arena.bytes[offset + 2]) << 8) | arena.bytes[offset + 3];
            };
            const uint32_t record = be(visible.r3.u32);
            check(record == lgi::scratch_sp(live_sp) + 0x80 && be(visible.r3.u32 + 4) == 0 &&
                  visible.r4.u32 == establisher && visible.r12.u32 == establisher,
                  "SDK unconsumed boundary delivers M4 filter pointers");
            check(be(record) == lgi::kGuestAccessViolation && be(record + 12) == guest_pc &&
                  be(record + 16) == 2 && be(record + 20) == 0 &&
                  be(record + 24) == mapping.page,
                  "real SDK callback then serialized guest PC/read/EA");
            return -1;
          }), {}});
      pgeh::Owner owner(guest, std::move(scopes)); owner.declare_label(guest_label);
      state.on_guest_fault = [&](uint32_t ea) {
        lgf::Record record{}; record.code = lgi::kGuestAccessViolation;
        record.pc = guest_pc; record.count = 2; record.info[1] = ea;
        lgi::deliver(arena, live_sp, record);
      };
      const auto selected = pgeh::region(owner, [&] {
        owner.set_pc(guest_pc); owner.before_call(); guest.r1.u64 = live_sp;
        check(state.dispatch(Stage::post_fault, static_cast<uint32_t>(mapping.page), page_address, kGuestSite,
                             Operation::kRead, value) == Result::guest_fault &&
                  state.watches == 2 && state.guest_dispatches == 1 && value == 0xfeedfaceu,
              "unconsumed valid synthetic guest read admitted");
      });
      state.on_guest_fault = {};
      check(selected == 0 && filters == 1 && cleanups == 0 && guest.r1.u32 == live_sp &&
            !lgi::current_delivery, "composed negative continuation preserves live owner");
    }
    check(state.dispatch(Stage::post_fault, 0, 0, kGuestSite, Operation::kRead, value) == Result::rejected &&
              state.guest_dispatches == 1 && state.watches == 2,
          "outside host address rejected without protection query");
    check(state.dispatch(Stage::post_fault, kMmioAddress, 0, kGuestSite, Operation::kRead, value) == Result::rejected &&
              state.reads == 1 && state.guest_dispatches == 1 && state.watches == 2,
          "host fault with MMIO-like guest EA has no MMIO side effect");
    check(state.dispatch(Stage::post_fault, static_cast<uint32_t>(mapping.page), page_address, kGuestSite,
                         Operation::kUnknown, value) == Result::rejected &&
              state.guest_dispatches == 1 && state.watches == 2,
          "unknown/execute operation rejected");
    check(state.dispatch(Stage::post_fault, static_cast<uint32_t>(mapping.page), page_address, kGuestSite + 4,
                         Operation::kRead, value) == Result::rejected &&
              state.guest_dispatches == 1 && state.watches == 3,
          "unconsumed wrong-site host fault rejected");
    mapping.protect(1, PageAccess::kReadWrite);
    state.handler = nullptr;
  }
  check(rex::runtime::MMIOHandler::global_handler() == nullptr,
        "SDK singleton lifetime ended before mapping teardown");
  std::printf("SDK_CONSUMERS PASS checks=%u\n", checks);
  return 0;
}
