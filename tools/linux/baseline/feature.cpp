// CPU-only C++ library/SDK-header gate. No runtime library, guest code or devices.
#include <atomic>
#include <bit>
#include <expected>
#include <format>
#include <iostream>
#include <thread>
#include <rex/result.h>
#include <rex/types.h>
#if !defined(__cpp_lib_expected) || __cpp_lib_expected < 202211L
#error expected monadic operations missing
#endif
#if !defined(__cpp_lib_format) || __cpp_lib_format < 201907L
#error format missing
#endif
#if !defined(__cpp_lib_byteswap) || __cpp_lib_byteswap < 202110L
#error byteswap missing
#endif
#if !defined(__cpp_lib_atomic_wait) || __cpp_lib_atomic_wait < 201907L
#error atomic wait missing
#endif
int main() {
  static_assert(std::byteswap(0x12345678u) == 0x78563412u);
  static_assert(rex::byte_swap(0x12345678u) == 0x78563412u);
  rex::Result<int> value = 20;
  auto result = value.transform([](int v) { return v + 1; })
      .and_then([](int v) -> rex::Result<int> { return v * 2; });
  rex::Result<int> error = std::unexpected(rex::Error{rex::ErrorCategory::IO, "probe"});
  auto recovered = error.or_else([](const rex::Error&) -> rex::Result<int> { return 42; });
  auto changed = error.transform_error([](const rex::Error&) { return 7; });
  std::atomic<int> signal{0};
  std::thread worker([&] { signal.store(1); signal.notify_one(); });
  signal.wait(0);
  worker.join();
  auto text = std::format("{}:{}", *result, *recovered);
  if (text != "42:42" || changed.error() != 7 || signal.load() != 1) return 1;
  std::cout << "R3HD_BASELINE_FEATURE PASS " << text << '\n';
}
