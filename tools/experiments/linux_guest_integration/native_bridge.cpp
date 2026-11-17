// Linux source preparation. New native outcomes remain UNKNOWN until executed.
#include "record_bridge.h"
#include "../linux_guest_fault/transport.h"
#include <cstdio>
#include <cstdlib>
#include <signal.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <unistd.h>

namespace {
unsigned checks = 0;
void check(bool value, const char* message) {
  ++checks;
  if (value) return;
  std::fprintf(stderr, "NATIVE_BRIDGE FAIL: %s\n", message);
  std::exit(2);
}
uint32_t read_be(std::span<uint8_t> bytes, uint32_t offset) {
  check(uint64_t(offset) + 4 <= bytes.size(), "filter pointer bounded");
  return (uint32_t(bytes[offset]) << 24) | (uint32_t(bytes[offset + 1]) << 16) |
         (uint32_t(bytes[offset + 2]) << 8) | bytes[offset + 3];
}
}

int main() {
  const rlimit no_core{0, 0};
  check(setrlimit(RLIMIT_CORE, &no_core) == 0, "disable core dumps");
  const long system_page = sysconf(_SC_PAGESIZE);
  check(system_page >= 4096 && system_page <= 65536, "supported fixture page size");
  const size_t page = static_cast<size_t>(system_page), size = page * 16;
  check(size <= UINT32_MAX, "guest arena representable");
  void* mapping = mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  check(mapping != MAP_FAILED, "anonymous synthetic arena");
  auto bytes = std::span<uint8_t>(static_cast<uint8_t*>(mapping), size);
  std::fill(bytes.begin(), bytes.end(), 0xa5);
  const uint32_t live_sp = static_cast<uint32_t>(page * 14);
  const uint32_t owner_sp = static_cast<uint32_t>(page * 15);
  constexpr uint32_t pc = 0x82001234, label = 0x82001300, ea = 0;
  lgi::GuestArena arena{bytes, static_cast<uint32_t>(page * 8), static_cast<uint32_t>(size),
                       true, page, reinterpret_cast<uintptr_t>(lgf_load_site)};
  check(lgf_process_install() == 0 && lgf_thread_attach() == 0, "isolated signal owner and TLS");
  unsigned backend_calls = 0;
  lgi::Backend backend = [&](const void* address) {
    ++backend_calls;
    uint32_t raw = 0xfeedface;
    const auto status = lgf_checked_load(mapping, size, address, &raw);
    if (status == LGF_LOAD_OK) return lgi::BackendResult::Success(raw);
    lgf_fault_info fault{};
    const bool admitted = status == LGF_LOAD_FAULT && lgf_last_fault(&fault) &&
        fault.signal_number == SIGSEGV && fault.signal_code == SEGV_ACCERR && fault.on_altstack &&
        fault.address == reinterpret_cast<uintptr_t>(address) &&
        fault.instruction == reinterpret_cast<uintptr_t>(lgf_load_site);
    check(raw == 0xfeedface, "captured load leaves raw output untouched");
    if (!admitted) return lgi::BackendResult::Reject();
    return lgi::BackendResult::Fault(fault.address, fault.instruction, true);
  };
  const std::array<lgi::Consumer, 0> none{};
  for (int disposition : {-1, 1}) {
    check(mprotect(mapping, page, PROT_NONE) == 0, "protect data page only");
    PPCContext state{}; state.r1.u64 = owner_sp; state.r14.u64 = 14; state.fpscr.InitHost();
    unsigned filters = 0, cleanups = 0;
    std::vector<pgeh::Scope> scopes;
    scopes.push_back({pc, pc + 4, 0, {}, [&](auto&, uint32_t) { ++cleanups; }});
    scopes.push_back({pc, pc + 4, label, lgi::wrap_filter([&](PPCContext& visible, const auto&, uint32_t establisher) {
      ++filters;
      const uint32_t scratch = lgi::scratch_sp(live_sp), pointers = visible.r3.u32;
      check(visible.r1.u32 == scratch && pointers == scratch + 0x70 &&
            visible.r4.u32 == owner_sp && visible.r12.u32 == owner_sp && establisher == owner_sp &&
            visible.r14.u64 == 14, "live scratch and owner filter arguments");
      const uint32_t record = read_be(bytes, pointers);
      check(record == scratch + 0x80 && read_be(bytes, pointers + 4) == 0, "M4 pointers and zero ContextRecord");
      check(read_be(bytes, record) == lgi::kGuestAccessViolation && read_be(bytes, record + 4) == 0 &&
            read_be(bytes, record + 8) == 0 && read_be(bytes, record + 12) == pc &&
            read_be(bytes, record + 16) == 2 && read_be(bytes, record + 20) == 0 &&
            read_be(bytes, record + 24) == ea, "hardware metadata serialized into M4 fields");
      for (uint32_t offset = 28; offset < 80; offset += 4)
        check(read_be(bytes, record + offset) == 0, "remaining record information zero");
      check(bytes[scratch + 0x6f] == 0xa5 && bytes[scratch + 0x78] == 0xa5 &&
            bytes[scratch + 0xd0] == 0xa5, "scratch canaries intact");
      if (disposition < 0) {
        check(mprotect(mapping, page, PROT_READ | PROT_WRITE) == 0, "filter repairs synthetic page");
        bytes[0] = 1; bytes[1] = 2; bytes[2] = 3; bytes[3] = 4;
        visible.r14.u64 = 99;
      }
      return disposition;
    }), {}});
    pgeh::Owner owner(state, std::move(scopes)); owner.declare_label(label);
    const auto selected = pgeh::region(owner, [&] {
      owner.set_pc(pc); owner.before_call(); state.r1.u64 = live_sp; state.r14.u64 = 42;
      uint32_t output = 0xdecafbad;
      const auto status = lgi::checked_load32(arena, {ea, pc, 4, lgi::Operation::read}, live_sp, none, backend, output);
      check(disposition < 0 && status == lgi::AccessStatus::guest_fault && output == 0xdecafbad &&
            cleanups == 0 && state.r1.u32 == live_sp && state.r14.u64 == 42,
            "negative returns to live invocation without premature cleanup");
      const unsigned before_retry = backend_calls;
      const auto retried = lgi::checked_load32(arena, {ea, pc, 4, lgi::Operation::read}, live_sp, none, backend, output);
      check(retried == lgi::AccessStatus::success && output == 0x01020304 &&
            backend_calls == before_retry + 1, "fresh helper retry once, big-endian result");
    });
    check(filters == 1 && selected == (disposition < 0 ? 0 : label) &&
          cleanups == (disposition < 0 ? 0u : 1u), "negative/accepted owner semantics");
    check(!lgi::current_delivery && !lgi::access_dispatch_active, "ordinary dispatch guards cleared");
  }
  check(backend_calls == 3, "no duplicated data loads");
  check(lgf_thread_detach() == 0 && lgf_process_uninstall() == 0, "quiescent transport teardown");
  check(munmap(mapping, size) == 0, "release owned arena");
  std::printf("NATIVE_BRIDGE PASS checks=%u\n", checks);
}
