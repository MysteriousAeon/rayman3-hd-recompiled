// Synthetic loop costs only; no signal capture or game performance claim.
#include "record_bridge.h"
#include <chrono>
#include <iomanip>
#include <iostream>

namespace {
template<class T> void escape(T& value) {
  __asm__ __volatile__("" : : "r"(&value) : "memory");
}
template<class F> void measure(const char* name, size_t count, F operation, bool& first) {
  using Clock = std::chrono::steady_clock;
  for (int i = 0; i < 1000; ++i) operation();
  std::vector<double> samples;
  for (int sample = 0; sample < 9; ++sample) {
    const auto start = Clock::now();
    for (size_t i = 0; i < count; ++i) operation();
    samples.push_back(std::chrono::duration<double, std::nano>(Clock::now() - start).count() / count);
  }
  std::sort(samples.begin(), samples.end());
  if (!first) std::cout << ",\n";
  first = false;
  std::cout << "  \"" << name << "\": {\"iterations_per_sample\":" << count
            << ",\"samples\":9,\"median_ns\":" << samples[4]
            << ",\"min_ns\":" << samples.front() << ",\"max_ns\":" << samples.back() << "}";
}
}

int main() {
  constexpr uint32_t pc = 0x82001234, label = 0x82001300, sp = 0xe000, ea = 0x1000;
  std::vector<uint8_t> bytes(0x10000, 0xa5);
  lgi::GuestArena arena{bytes, 0x8000, 0x10000, true, 4096, 0x12345678};
  lgi::AccessRequest request{ea, pc, 4, lgi::Operation::read};
  std::array<lgi::Consumer, 0> none{};
  lgi::Backend backend = [](const void* address) {
    uint32_t raw;
    std::memcpy(&raw, address, sizeof(raw));
    return lgi::BackendResult::Success(raw);
  };
  const std::array<lgi::Consumer, 1> consumer{{[](const auto&, uintptr_t) {
    return lgi::ConsumerResult::Mmio(0x12345678);
  }}};
  auto metadata = lgi::BackendResult::Fault(reinterpret_cast<uintptr_t>(bytes.data() + ea),
                                           arena.admitted_read_site, true);
  lgf::Record record{};
  record.code = lgi::kGuestAccessViolation; record.pc = pc; record.count = 2; record.info[1] = ea;
  uint32_t output = 0, scratch = 0, pointers = 0;
  bool first = true;
  std::cout << std::fixed << std::setprecision(3) << "{\n";
  measure("unchecked_be32", 100000, [&] {
    uint32_t raw;
    std::memcpy(&raw, bytes.data() + ea, sizeof(raw));
    output = lgi::host_to_guest_be32(raw); escape(output);
  }, first);
  measure("checked_success", 100000, [&] {
    auto status = lgi::checked_load32(arena, request, sp, none, backend, output);
    escape(status); escape(output);
  }, first);
  measure("checked_one_mmio_consumer", 100000, [&] {
    auto status = lgi::checked_load32(arena, request, sp, consumer, backend, output);
    escape(status); escape(output);
  }, first);
  measure("fault_metadata_classification", 100000, [&] {
    escape(metadata);
    bool admitted = lgi::admits_fault(arena, reinterpret_cast<uintptr_t>(bytes.data() + ea), metadata);
    escape(admitted);
  }, first);
  measure("record_preflight_and_serialization", 100000, [&] {
    bool valid = lgi::can_serialize(arena, sp, record) &&
        lgf::push(bytes, sp, arena.stack_low, arena.stack_high, record, scratch, pointers);
    escape(valid); escape(bytes); escape(scratch); escape(pointers);
  }, first);
  PPCContext state{}; state.r1.u64 = sp; state.fpscr.InitHost();
  for (int disposition : {-1, 1}) {
    std::vector<pgeh::Scope> scopes;
    scopes.push_back({pc, pc + 4, label, lgi::wrap_filter(
        [disposition](auto&, const auto&, uint32_t) { return disposition; }), {}});
    pgeh::Owner owner(state, std::move(scopes));
    owner.declare_label(label); owner.set_pc(pc);
    measure(disposition < 0 ? "negative_delivery_one_filter" : "accepted_delivery_same_owner",
            disposition < 0 ? 10000 : 2000, [&] {
      auto selected = pgeh::region(owner, [&] { lgi::deliver(arena, sp, record); });
      escape(selected); escape(state); escape(bytes);
    }, first);
  }
  std::cout << "\n}\n";
}
