// Source-only feasibility fixture; all modes are synthetic and native Linux
// x86-64 only. Crash modes must each be run as a separate child process.
#define _GNU_SOURCE 1
#include "transport.h"
#include "../portable_guest_eh/exception_core.h"

#include <array>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <signal.h>
#include <string>
#include <sys/mman.h>
#include <sys/resource.h>
#include <unistd.h>
#include <vector>
#include <pthread.h>

namespace {
constexpr uint32_t kGuestPc = 0x82001234;
constexpr uint32_t kHandlerLabel = 0x82001300;
constexpr uint32_t kGuestAv = 0xc0000005;

void check(bool ok, const char *what) {
  if (ok) return;
  std::fprintf(stderr, "LGF_FIXTURE FAIL: %s\n", what);
  std::exit(2);
}

struct Page {
  void *base = MAP_FAILED;
  size_t size = 0;
  Page() {
    long p = sysconf(_SC_PAGESIZE);
    check(p > 0, "page size");
    size = (size_t)p;
    base = mmap(nullptr, size, PROT_READ | PROT_WRITE,
                MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    check(base != MAP_FAILED, "mmap page");
    *static_cast<uint32_t *>(base) = 0x12345678;
  }
  ~Page() { if (base != MAP_FAILED) (void)munmap(base, size); }
  void protect() { check(mprotect(base, size, PROT_NONE) == 0, "mprotect none"); }
  void repair(uint32_t value) {
    check(mprotect(base, size, PROT_READ | PROT_WRITE) == 0, "mprotect repair");
    *static_cast<uint32_t *>(base) = value;
  }
};

struct PriorConfig {
  uintptr_t mmio = 0;
  uintptr_t watch = 0;
  unsigned mmio_calls = 0;
  unsigned watch_calls = 0;
  unsigned dispatch_calls = 0;
};
enum lgf_prior_result prior_memory_handler(uintptr_t address, uint32_t *out,
                                           void *opaque) {
  auto &state = *static_cast<PriorConfig *>(opaque);
  if (address == state.mmio) {
    ++state.mmio_calls;
    *out = 0xaabbccdd;
    return LGF_PRIOR_MMIO;
  }
  if (address == state.watch) {
    ++state.watch_calls;
    return LGF_PRIOR_WATCH;
  }
  return LGF_PRIOR_PASS;
}

PPCContext new_context() {
  PPCContext state{};
  state.r1.u64 = 0x30000;
  return state;
}

void accepted_parent_transfer() {
  Page page;
  page.protect();
  auto state = new_context();
  std::vector<std::string> order;
  std::vector<pgeh::Scope> outer_scopes;
  outer_scopes.push_back({kGuestPc - 4, kGuestPc + 4, 0, {}, [&](auto &, uint32_t) {
    order.emplace_back("outer-finally");
  }});
  outer_scopes.push_back({kGuestPc - 4, kGuestPc + 4, kHandlerLabel,
      [&](auto &, const auto &, uint32_t) { return 1; }, {}});
  pgeh::Owner outer(state, std::move(outer_scopes));
  outer.declare_label(kHandlerLabel);
  const uint32_t selected = pgeh::region(outer, [&] {
    outer.set_pc(kGuestPc);
    outer.before_call();
    std::vector<pgeh::Scope> inner_scopes;
    inner_scopes.push_back({kGuestPc - 4, kGuestPc + 4, 0, {}, [&](auto &, uint32_t) {
      order.emplace_back("inner-finally");
    }});
    pgeh::Owner inner(state, std::move(inner_scopes));
    (void)pgeh::region(inner, [&] {
      inner.set_pc(kGuestPc);
      inner.before_call();
      struct HostCleanup {
        std::vector<std::string> &order;
        ~HostCleanup() { order.emplace_back("host-destructor"); }
      } host_cleanup{order};
      uint32_t value = 0xfeedface;
      auto status = lgf_checked_load(page.base, page.size, page.base, &value);
      check(status == LGF_LOAD_FAULT, "accepted path captures guest page fault");
      check(value == 0xfeedface, "faulting leaf leaves output unchanged");
      lgf_fault_info fault{};
      check(lgf_last_fault(&fault) && fault.signal_number == SIGSEGV &&
            fault.signal_code == SEGV_ACCERR && fault.address == (uintptr_t)page.base &&
            fault.instruction == (uintptr_t)lgf_load_site && fault.on_altstack,
            "accepted path metadata identifies exact guest site");
      inner.after_call();
      pgeh::raise({kGuestAv, 0, kGuestPc});
    });
  });
  check(selected == kHandlerLabel, "accepted transfer returns owner label");
  check(order == std::vector<std::string>{"host-destructor", "inner-finally", "outer-finally"},
        "host destructor precedes inner and outer guest cleanup");
}

void negative_filter_and_fresh_call() {
  Page page;
  page.protect();
  auto state = new_context();
  unsigned filters = 0;
  std::vector<pgeh::Scope> scopes;
  scopes.push_back({kGuestPc - 4, kGuestPc + 4, kHandlerLabel,
      [&](auto &, const auto &record, uint32_t) {
        ++filters;
        check(record.code == kGuestAv && record.address == kGuestPc,
              "negative filter sees synthetic guest record");
        page.repair(0x76543210);
        return -1;
      }, {}});
  pgeh::Owner owner(state, std::move(scopes));
  owner.declare_label(kHandlerLabel);
  const uint32_t label = pgeh::region(owner, [&] {
    owner.set_pc(kGuestPc);
    owner.before_call();
    uint32_t value = 0;
    auto status = lgf_checked_load(page.base, page.size, page.base, &value);
    check(status == LGF_LOAD_FAULT, "negative path captures initial fault");
    owner.after_call();
    pgeh::raise({kGuestAv, 0, kGuestPc});
    // The operation is retried by a new checked-helper call in ordinary code.
    // This says nothing about retrying an arbitrary interrupted instruction.
    status = lgf_checked_load(page.base, page.size, page.base, &value);
    check(status == LGF_LOAD_OK && value == 0x76543210,
          "repaired operation succeeds on explicit fresh call");
  });
  check(label == 0 && filters == 1, "negative disposition resumes same owner");
}

void same_owner_and_invalid_destination() {
  Page page;
  page.protect();
  auto state = new_context();
  std::vector<pgeh::Scope> scopes;
  scopes.push_back({kGuestPc - 4, kGuestPc + 4, kHandlerLabel,
      [](auto &, const auto &, uint32_t) { return 1; }, {}});
  pgeh::Owner owner(state, std::move(scopes));
  owner.declare_label(kHandlerLabel);
  const uint32_t label = pgeh::region(owner, [&] {
    owner.set_pc(kGuestPc);
    owner.before_call();
    uint32_t out = 0;
    check(lgf_checked_load(page.base, page.size, page.base, &out) == LGF_LOAD_FAULT,
          "same-owner fault captured");
    owner.after_call();
    pgeh::raise({kGuestAv, 0, kGuestPc});
  });
  check(label == kHandlerLabel, "same-owner accepted label");
  bool rejected = false;
  try {
    pgeh::request_unwind({UINT64_MAX, UINT64_MAX}, kHandlerLabel, 0);
  } catch (const pgeh::Unsupported &) {
    rejected = true;
  }
  check(rejected, "invalid destination rejected by portable emitter");
}

void consumed_handlers_first() {
  Page page;
  page.protect();
  PriorConfig prior{(uintptr_t)page.base, (uintptr_t)page.base + 4};
  lgf_set_prior_handler(prior_memory_handler, &prior);
  uint32_t out = 0;
  auto mmio = lgf_checked_load(page.base, page.size, page.base, &out);
  if (mmio == LGF_LOAD_FAULT) ++prior.dispatch_calls;
  check(mmio == LGF_LOAD_MMIO_CONSUMED &&
        out == 0xaabbccdd, "stand-in MMIO handler consumes before guest adapter");
  auto watch = lgf_checked_load(page.base, page.size, (char *)page.base + 4, &out);
  if (watch == LGF_LOAD_FAULT) ++prior.dispatch_calls;
  check(watch == LGF_LOAD_WATCH_CONSUMED,
        "stand-in watch handler consumes before guest adapter");
  check(prior.mmio_calls == 1 && prior.watch_calls == 1 && prior.dispatch_calls == 0,
        "consumed MMIO/watch paths do not enter guest dispatch");
  lgf_set_prior_handler(nullptr, nullptr);
}

void boundaries_and_unrepaired_fault() {
  Page page;
  uint32_t out = 0xabcdef01;
  const uintptr_t base = reinterpret_cast<uintptr_t>(page.base);
  auto at = [](uintptr_t value) { return reinterpret_cast<const void *>(value); };
  check(lgf_checked_load(page.base, page.size, at(base - 1), &out) == LGF_LOAD_REJECTED,
        "reject below arena");
  check(lgf_checked_load(page.base, page.size, at(base + page.size), &out) == LGF_LOAD_REJECTED,
        "reject one-past arena");
  check(lgf_checked_load(page.base, page.size, at(base + page.size - 3), &out) == LGF_LOAD_REJECTED,
        "reject access crossing arena end");
  check(lgf_checked_load(at(UINTPTR_MAX - 3), 8, at(UINTPTR_MAX - 3), &out) == LGF_LOAD_REJECTED,
        "reject wrapping arena");
  check(lgf_checked_load(page.base, 0, page.base, &out) == LGF_LOAD_REJECTED,
        "reject empty arena");
  check(lgf_checked_load(page.base, page.size, at(base + 1), &out) == LGF_LOAD_REJECTED,
        "reject unaligned helper access");
  check(out == 0xabcdef01, "rejections do not alter output");
  auto *last = reinterpret_cast<uint32_t *>(base + page.size - 4);
  *last = 0x10203040;
  check(lgf_checked_load(page.base, page.size, last, &out) == LGF_LOAD_OK && out == 0x10203040,
        "last full-width access succeeds");
  sigset_t blocked{}, old{};
  sigemptyset(&blocked); sigaddset(&blocked, SIGSEGV);
  check(pthread_sigmask(SIG_BLOCK, &blocked, &old) == 0, "block signal for refusal test");
  check(lgf_checked_load(page.base, page.size, page.base, &out) == LGF_LOAD_REJECTED,
        "refuse blocked hardware signal");
  check(pthread_sigmask(SIG_SETMASK, &old, nullptr) == 0, "restore test mask");
  page.protect();
  out = 0xfeedface;
  for (unsigned i = 0; i != 2; ++i)
    check(lgf_checked_load(page.base, page.size, page.base, &out) == LGF_LOAD_FAULT && out == 0xfeedface,
          "unrepaired fresh call remains a fault");
}

struct ThreadProbe {
  void *address = nullptr;
  size_t size = 0;
  int status = -1;
  int attached = -1;
  int detached = -1;
};
void *thread_probe(void *opaque) {
  auto &probe = *static_cast<ThreadProbe *>(opaque);
  probe.attached = lgf_thread_attach();
  if (probe.attached) return nullptr;
  (void)mprotect(probe.address, probe.size, PROT_NONE);
  uint32_t out = 0;
  probe.status = lgf_checked_load(probe.address, probe.size, probe.address, &out);
  lgf_fault_info info{};
  if (!lgf_last_fault(&info) || info.address != (uintptr_t)probe.address ||
      !info.on_altstack || info.count != 1 || info.signal_number != SIGSEGV)
    probe.status = LGF_LOAD_REJECTED;
  probe.detached = lgf_thread_detach();
  return nullptr;
}
void cross_thread_slots() {
  lgf_fault_info main_before{}, main_after{};
  check(lgf_last_fault(&main_before), "main slot populated before thread probes");
  Page pages[2];
  ThreadProbe probes[2]{{pages[0].base, pages[0].size},
                        {pages[1].base, pages[1].size}};
  check(probes[0].address != probes[1].address, "distinct thread test pages");
  pthread_t threads[2];
  check(pthread_create(&threads[0], nullptr, thread_probe, &probes[0]) == 0,
        "create first probe thread");
  check(pthread_create(&threads[1], nullptr, thread_probe, &probes[1]) == 0,
        "create second probe thread");
  check(pthread_join(threads[0], nullptr) == 0 && pthread_join(threads[1], nullptr) == 0,
        "join probe threads");
  check(probes[0].attached == 0 && probes[1].attached == 0 &&
        probes[0].detached == 0 && probes[1].detached == 0 &&
        probes[0].status == LGF_LOAD_FAULT && probes[1].status == LGF_LOAD_FAULT &&
        probes[0].address && probes[1].address && probes[0].address != probes[1].address,
        "concurrent threads retain distinct per-thread fault slots");
  check(lgf_last_fault(&main_after) && main_before.address == main_after.address &&
        main_before.count == main_after.count, "thread probes leave main slot unchanged");
}

void normal_mode() {
  check(lgf_process_install() == 0, "install isolated SIGSEGV adapter");
  check(lgf_thread_attach() == 0, "attach main thread alternate stack");
  accepted_parent_transfer();
  negative_filter_and_fresh_call();
  same_owner_and_invalid_destination();
  consumed_handlers_first();
  boundaries_and_unrepaired_fault();
  cross_thread_slots();
  check(lgf_thread_detach() == 0, "detach main thread");
  check(lgf_process_uninstall() == 0, "restore SIGSEGV disposition");
  std::puts("LGF_FIXTURE PASS mode=normal classification=synthetic recovery=checked-leaf");
}

void prior_handler_mode() {
  struct sigaction old_action{}, dummy{};
  dummy.sa_handler = SIG_IGN;
  sigemptyset(&dummy.sa_mask);
  check(sigaction(SIGSEGV, &dummy, &old_action) == 0, "install stand-in prior owner");
  int rc = lgf_process_install();
  check(rc == EBUSY, "refuse to replace prior SIGSEGV handler");
  check(sigaction(SIGSEGV, &old_action, nullptr) == 0, "restore prior signal owner");
  std::puts("LGF_FIXTURE PASS mode=prior-handler result=refused");
}

[[noreturn]] void crash_mode(const std::string &mode) {
  if (mode == "unsupported-bus") {
    check(lgf_process_install() == 0 && lgf_thread_attach() == 0,
          "install before SIGBUS case");
    (void)raise(SIGBUS);
    std::exit(3);
  }
  if (mode == "host-null") {
    check(lgf_process_install() == 0 && lgf_thread_attach() == 0,
          "install before host-null case");
    uint32_t out = 0;
    (void)lgf_load32(nullptr, &out); // Unarmed; expected default SIGSEGV.
    std::exit(3);
  }
  if (mode == "host-outside") {
    check(lgf_process_install() == 0 && lgf_thread_attach() == 0,
          "install before host-outside case");
    Page outside;
    outside.protect();
    uint32_t out = 0;
    (void)lgf_load32(outside.base, &out); // Not declared as any guest arena.
    std::exit(3);
  }
  Page page;
  page.protect();
  uint32_t out = 0;
  if (mode == "unarmed") {
    check(lgf_process_install() == 0 && lgf_thread_attach() == 0,
          "install before unarmed case");
    (void)lgf_load32(page.base, &out);
    std::exit(3);
  }
  if (mode == "wrong-site") {
    check(lgf_process_install() == 0 && lgf_thread_attach() == 0,
          "install before wrong-site case");
    (void)lgf_test_wrong_site(page.base, page.size, page.base, &out);
    std::exit(3);
  }
  if (mode == "reentrant") {
    check(lgf_process_install() == 0 && lgf_thread_attach() == 0,
          "install before reentrant case");
    lgf_test_reentrant_mode(1);
    (void)lgf_checked_load(page.base, page.size, page.base, &out);
    std::exit(3);
  }
  std::fprintf(stderr, "unknown crash mode: %s\n", mode.c_str());
  std::exit(2);
}
} // namespace

int main(int argc, char **argv) {
  const struct rlimit no_core{0, 0};
  check(setrlimit(RLIMIT_CORE, &no_core) == 0, "disable core files for fault children");
  const std::string mode = argc > 1 ? argv[1] : "normal";
  if (mode == "normal") { normal_mode(); return 0; }
  if (mode == "prior-handler") { prior_handler_mode(); return 0; }
  crash_mode(mode);
}
