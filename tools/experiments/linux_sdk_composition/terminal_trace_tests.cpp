// Portable ordinary-code contract checks. No native fault or signal claim.
#include "terminal_trace.h"
#include <cstdlib>

namespace {
unsigned checks;
void check(bool ok) { ++checks; if (!ok) std::exit(1); }
}
int main(int argc, char** argv) {
  check(argc == 2);
  std::FILE* file = nullptr;
#ifdef _WIN32
  check(fopen_s(&file, argv[1], "wb") == 0);
#else
  file = std::fopen(argv[1], "wb");
#endif
  check(file != nullptr);
  constexpr const char* token = "0123456789abcdef0123456789abcdef";
  check(lsc_gate::valid_token(token));
  check(!lsc_gate::valid_token(nullptr) && !lsc_gate::valid_token("x") &&
        !lsc_gate::valid_token("0123456789abcdef0123456789abcdeF"));
  for (auto mode : {lsc_gate::Mode::callback, lsc_gate::Mode::repair, lsc_gate::Mode::unhandled}) {
    lsc_gate::Witness w(mode, token, 10, 20);
    w.facts.address = 0x1000;
    check(!w.emit("terminal", file)); // A premature terminal claim is rejected.
    check(!w.consumers(9, 20));
    w.facts.attempts = w.facts.faults = 1;
    check(w.consumers(11, mode == lsc_gate::Mode::callback ? 21 : 20));
    w.facts.filters = mode == lsc_gate::Mode::unhandled ? 1 : 0;
    const char* first = mode == lsc_gate::Mode::callback ? "injected" :
                        mode == lsc_gate::Mode::repair ? "claimed" : "filter_search";
    check(w.emit(first, file));
    check(!w.emit(first, file)); // Duplicated earlier phase cannot advance.
    if (mode == lsc_gate::Mode::repair) w.facts.attempts = w.facts.faults = 2;
    else w.facts.caught = 1;
    w.facts.address = 0x2000;
    check(!w.emit(mode == lsc_gate::Mode::repair ? "retry_fault" : "caught", file));
    w.facts.address = 0x1000;
    check(w.emit(mode == lsc_gate::Mode::repair ? "retry_fault" : "caught", file));
    check(w.emit("terminal", file));
    check(!w.emit("terminal", file));
  }
  check(std::fclose(file) == 0);
  std::printf("TERMINAL_TRACE_CONTRACT PASS checks=%u\n", checks);
}
