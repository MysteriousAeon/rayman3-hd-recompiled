// Synthetic microbenchmarks only; these are not in-game overhead measurements.
#include "exception_core.h"
#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <string>

namespace {
template<class T> void escape(T& object) {
#if defined(__clang__) || defined(__GNUC__)
  __asm__ __volatile__("" : : "r"(&object) : "memory");
#else
#error Benchmark requires the documented Clang/GCC toolchain.
#endif
}
template<class Operation>
void measure(const char* name, size_t iterations, Operation operation, bool& first) {
  using Clock = std::chrono::steady_clock;
  for (int i = 0; i < 1000; ++i) operation();
  std::vector<double> samples;
  for (int repeat = 0; repeat < 9; ++repeat) {
    const auto start = Clock::now();
    for (size_t i = 0; i < iterations; ++i) operation();
    const auto finish = Clock::now();
    samples.push_back(std::chrono::duration<double, std::nano>(finish - start).count() / iterations);
  }
  std::sort(samples.begin(), samples.end());
  if (!first) std::cout << ",\n";
  first = false;
  std::cout << "  \"" << name << "\": {\"iterations_per_sample\":" << iterations
            << ",\"samples\":9,\"median_ns\":" << samples[4]
            << ",\"min_ns\":" << samples.front() << ",\"max_ns\":" << samples.back() << "}";
}
}
int main() {
  using namespace pgeh;
  Adapter::State state{};
  state.r1.u64 = 0x10000;
  state.fpscr.InitHost();
  bool first = true;
  std::cout << std::fixed << std::setprecision(3) << "{\n";
  measure("baseline_state_increment", 100000, [&] { ++state.r3.u64; escape(state); }, first);
  measure("empty_owner_construct_destroy", 100000, [&] {
    Owner owner(state, {}); escape(owner);
  }, first);
  {
    Owner owner(state, {});
    measure("guest_pc_tracking", 100000, [&] { owner.set_pc(12); escape(owner); }, first);
    measure("owner_snapshot", 50000, [&] {
      auto saved = Adapter::capture_owner(state); escape(saved);
    }, first);
    const auto saved = Adapter::capture_owner(state);
    measure("owner_restore", 50000, [&] {
      Adapter::restore_owner(state, saved); escape(state);
    }, first);
    measure("full_snapshot_restore", 20000, [&] {
      auto full = Adapter::capture_full(state); escape(full);
      Adapter::restore_full(state, full); escape(state);
    }, first);
    measure("normal_region_pc_increment", 50000, [&] {
      auto target = region(owner, [&] { owner.set_pc(12); ++state.r3.u64; }); escape(target); escape(state);
    }, first);
  }
  {
    Owner owner(state, {{10, 20, 30,
      [](Adapter::State&, const GuestRecord&, uint32_t) { return -1; }, {}}});
    owner.declare_label(30); owner.set_pc(12);
    measure("negative_search_one_filter", 10000, [&] { raise({1, 0, 12}); escape(state); }, first);
  }
  {
    Owner owner(state, {{10, 20, 30,
      [](Adapter::State&, const GuestRecord&, uint32_t) { return 1; }, {}}});
    owner.declare_label(30); owner.set_pc(12);
    measure("accepted_search_transfer", 2000, [&] {
      auto target = region(owner, [] { raise({1, 0, 12}); }); escape(target); escape(state);
    }, first);
  }
  std::cout << "\n}\n";
}
