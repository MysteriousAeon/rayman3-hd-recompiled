// M23 (D-053): the hidden-run haptics policy, deterministic checks. Host-only, no device, no game material.
#include "m23_haptics.h"
#include <cstdio>
#include <cstring>

static int checks = 0, failures = 0;
static void Check(bool ok, const char* what) {
  ++checks;
  if (!ok) {
    ++failures;
    std::printf("FAIL %s\n", what);
  }
}

int main() {
  using namespace m23haptics;
  // Hidden = the variable exists, whatever its value: there is no value that makes a hidden run audible to a
  // controller, and no second variable.
  Check(!HiddenRun(nullptr), "no variable: a visible session, vibration untouched");
  Check(HiddenRun("1") && HiddenRun("") && HiddenRun("0") && HiddenRun("off"), "any value of the variable is a hidden run");
  Check(PhysicalPadDriversAllowed(false), "visible session: pad drivers as before");
  Check(!PhysicalPadDriversAllowed(true), "hidden run: no physical pad driver");
  // The answer a hidden run gives the title: success for the test source's pad, not connected for the others.
  Check(HiddenSetStateResult(0) == 0 && HiddenSetStateResult(0xFF) == 0 && HiddenSetStateResult(0x1FF) == 0, "pad 0 / any user: success");
  Check(HiddenSetStateResult(1) == 0x48F && HiddenSetStateResult(2) == 0x48F && HiddenSetStateResult(3) == 0x48F, "other pads: not connected");
  // The marker the hidden runner looks for is the log format itself, so it cannot exist without the log line.
  Check(std::strstr(kMarker, "M23 haptics policy=") == kMarker, "marker starts with the policy text");
  Check(Answered().load() == 0 && StoppedAtSink().load() == 0, "counters start at zero");
  ++Answered();
  Check(Answered().load() == 1 && StoppedAtSink().load() == 0, "counters are independent");
  std::printf("M23_HAPTICS_TEST %s checks=%d failures=%d\n", failures ? "FAIL" : "PASS", checks, failures);
  return failures ? 1 : 0;
}
