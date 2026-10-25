// M8 crash-report regression fixture: `crash_test fault` dies on a null write with the reporter
// installed; `crash_test ok` exits normally. Driven by tools/m8_crash_regression.py.
#include "m8_crash_report.h"
#include <cstring>

static int Describe(char* out, int size) {
  return std::snprintf(out, size, "last_entered_function=fixture_function lr=82001234 sp=70001000\n");
}

int main(int argc, char** argv) {
  m8crash::Install(Describe);
  if (argc == 2 && !std::strcmp(argv[1], "ok")) return 0;
  if (argc == 2 && !std::strcmp(argv[1], "fault")) {
    volatile int* target = nullptr;
    *target = 1;
    return 3;  // not reached
  }
  return 2;
}
