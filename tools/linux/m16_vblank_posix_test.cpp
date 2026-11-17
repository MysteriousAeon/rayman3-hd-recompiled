// LM-1: host test of the POSIX deadline wait in m16_vblank.h (no SDK, no game). The guest clock is the host
// steady clock at 50 MHz, as the pinned runtime's guest tick frequency.
#include <chrono>
#include <cstdio>
#include <cstdlib>

#include "m16_vblank.h"  // <rex/logging.h> comes from tools/linux/test_stub

namespace {
constexpr uint64_t kFreq = 50000000ull;
uint64_t Now() {
  return uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(
                      std::chrono::steady_clock::now().time_since_epoch()).count() / 20);
}
int failures = 0;
void Check(bool ok, const char* what, long long value) {
  std::printf("%s %s (%lld us)\n", ok ? "ok  " : "FAIL", what, value);
  if (!ok) ++failures;
}
long long WaitUs(uint64_t deadline) {
  const uint64_t t0 = Now();
  m16vb::WaitForDeadline(deadline, kFreq, Now);
  return (long long)((Now() - t0) * 1000000ull / kFreq);
}
}  // namespace

int main() {
  // Past deadline and zero frequency return at once.
  Check(WaitUs(Now() - 1000) < 1000, "past deadline returns immediately", WaitUs(Now() - 1000));
  {
    const uint64_t t0 = Now();
    m16vb::WaitForDeadline(Now() + kFreq, 0, Now);
    Check((Now() - t0) * 1000000ull / kFreq < 1000, "zero frequency returns immediately",
          (long long)((Now() - t0) * 1000000ull / kFreq));
  }
  // A far deadline is a bounded leg (about 4 ms sleep), never a long block.
  const long long far = WaitUs(Now() + kFreq);  // 1 s away
  Check(far >= 3000 && far < 20000, "far deadline: one bounded leg of about 4 ms", far);
  // A near deadline (2 ms) is reached, not overshot by more than a scheduler quantum.
  for (int i = 0; i < 20; ++i) {
    const uint64_t deadline = Now() + kFreq / 500;  // 2 ms
    m16vb::WaitForDeadline(deadline, kFreq, Now);
    const long long late = (long long)Now() - (long long)deadline;
    if (i < 3 || late < 0 || late * 1000000 / (long long)kFreq > 3000)
      Check(late >= 0 && late * 1000000 / (long long)kFreq <= 3000, "2 ms deadline reached, lateness <= 3 ms",
            late * 1000000 / (long long)kFreq);
  }
  // Repeated calls until a 16.667 ms deadline (the vblank loop) end at or after it.
  const uint64_t deadline = Now() + kFreq / 60;
  int calls = 0;
  while (Now() < deadline && calls < 100) {
    m16vb::WaitForDeadline(deadline, kFreq, Now);
    ++calls;
  }
  Check(Now() >= deadline && calls >= 1 && calls <= 10, "vblank interval reached in bounded calls", calls);
  std::printf("M16_POSIX_TEST %s failures=%d\n", failures ? "FAIL" : "PASS", failures);
  return failures ? 1 : 0;
}
