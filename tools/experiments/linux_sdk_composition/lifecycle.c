// Subprocess-only synthetic ownership and exact-access tests.
#define _GNU_SOURCE 1
#include "transport.h"
#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>

int lsc_wrong_leaf(const void*);
static unsigned checks;
static void check(int condition, const char* description) {
  ++checks;
  if (!condition) { fprintf(stderr, "LSC FAIL: %s\n", description); exit(2); }
}
static void ignored_handler(int sig) { (void)sig; }
static void set_action(void (*fn)(int)) {
  struct sigaction action = {0};
  action.sa_handler = fn;
  sigemptyset(&action.sa_mask);
  check(sigaction(SIGSEGV, &action, NULL) == 0, "set subprocess action");
}
static size_t page_size(void) {
  long page = sysconf(_SC_PAGESIZE);
  check(page >= 4096, "page size");
  return (size_t)page;
}
static void* page_new(size_t page) {
  void* p = mmap(NULL, page, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  check(p != MAP_FAILED, "anonymous page");
  *(uint32_t*)p = UINT32_C(0x12345678);
  return p;
}
static int same_action(const struct sigaction* a, const struct sigaction* b) {
  if (a->sa_handler != b->sa_handler || a->sa_flags != b->sa_flags) return 0;
  for (int sig = 1; sig < NSIG; ++sig)
    if (sigismember(&a->sa_mask, sig) != sigismember(&b->sa_mask, sig)) return 0;
  return 1;
}
static void test_ordinary(void) {
  uint32_t value = 5;
  check(lsc_read32(&value, sizeof(value), &value, &value) == LSC_NOT_ATTACHED,
        "unattached access refused");
  check(lsc_write32(&value, sizeof(value), &value, 7) == LSC_NOT_ATTACHED && value == 5,
        "unattached store has no side effect");
  check(lsc_uninstall() == EINVAL && lsc_attach() == EINVAL && lsc_detach() == EINVAL,
        "lifecycle rejects invalid order");
}
struct thread_arg { pthread_barrier_t* ready; pthread_barrier_t* finish; int ok; unsigned index; };
static void* thread_entry(void* ptr) {
  struct thread_arg* arg = ptr;
  size_t page = (size_t)sysconf(_SC_PAGESIZE);
  void* map = mmap(NULL, page, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  int ok = page >= 4096 && map != MAP_FAILED && lsc_attach() == 0;
  if (ok) {
    *(uint32_t*)map = arg->index + 100;
    ok = mprotect(map, page, PROT_NONE) == 0;
    uint32_t output = UINT32_C(0xdeadbeef);
    struct lsc_fault fault = {0};
    ok = ok && lsc_read32(map, page, map, &output) == LSC_FAULT &&
         output == UINT32_C(0xdeadbeef) && lsc_last_fault(&fault) &&
         fault.address == (uintptr_t)map && fault.instruction == (uintptr_t)lsc_read_site &&
         fault.operation == LSC_READ && fault.count == 1 && fault.on_altstack;
  }
  arg->ok = ok;
  (void)pthread_barrier_wait(arg->ready);
  (void)pthread_barrier_wait(arg->finish);
  if (ok) arg->ok = lsc_detach() == 0;
  if (map != MAP_FAILED) (void)munmap(map, page);
  return NULL;
}
static void threads_test(void) {
  pthread_barrier_t ready, finish;
  pthread_t threads[2];
  struct thread_arg args[2];
  check(pthread_barrier_init(&ready, NULL, 3) == 0 && pthread_barrier_init(&finish, NULL, 3) == 0,
        "thread barriers");
  for (unsigned i = 0; i < 2; ++i) {
    args[i] = (struct thread_arg){&ready, &finish, 0, i};
    check(pthread_create(&threads[i], NULL, thread_entry, &args[i]) == 0, "start thread");
  }
  (void)pthread_barrier_wait(&ready);
  check(args[0].ok && args[1].ok, "independent TLS fault metadata");
  check(lsc_uninstall() == EBUSY, "other threads prevent uninstall");
  (void)pthread_barrier_wait(&finish);
  for (unsigned i = 0; i < 2; ++i)
    check(pthread_join(threads[i], NULL) == 0 && args[i].ok, "join detached thread");
  check(pthread_barrier_destroy(&ready) == 0 && pthread_barrier_destroy(&finish) == 0,
        "destroy barriers");
}
static void normal(void) {
  struct sigaction custom = {0}, before, after;
  custom.sa_handler = SIG_DFL;
  custom.sa_flags = SA_RESTART;
  sigemptyset(&custom.sa_mask); sigaddset(&custom.sa_mask, SIGUSR1);
  check(sigaction(SIGSEGV, &custom, NULL) == 0 && sigaction(SIGSEGV, NULL, &before) == 0,
        "set default action with nonempty mask");
  check(lsc_install() == 0 && lsc_install() == EALREADY, "exclusive install");
  size_t alternate_size = 1024u * 1024u;
  void* alternate = mmap(NULL, alternate_size, PROT_READ | PROT_WRITE,
                         MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  check(alternate != MAP_FAILED, "foreign alternate stack allocation");
  stack_t foreign = {0}, old_stack, actual_stack;
  foreign.ss_sp = alternate; foreign.ss_size = alternate_size;
  check(sigaltstack(&foreign, &old_stack) == 0 && lsc_attach() == EBUSY &&
        sigaltstack(NULL, &actual_stack) == 0 && actual_stack.ss_sp == alternate,
        "foreign alternate stack is preserved");
  check(sigaltstack(&old_stack, NULL) == 0 && munmap(alternate, alternate_size) == 0,
        "foreign alternate stack teardown");
  check(lsc_attach() == 0 && lsc_attach() == EALREADY, "attach and double attach");
  check(lsc_uninstall() == EBUSY, "attached caller prevents uninstall");
  size_t page = page_size();
  void* map = page_new(page);
  uint32_t output = 0;
  check(lsc_read32(map, page, map, &output) == LSC_OK && output == UINT32_C(0x12345678),
        "normal read");
  check(lsc_read32(map, page, (char*)map + 1, &output) == LSC_REJECTED &&
        lsc_read32(map, page, (char*)map + page, &output) == LSC_REJECTED,
        "alignment and bounds rejection");
  sigset_t set, old;
  sigemptyset(&set); sigaddset(&set, SIGSEGV);
  check(pthread_sigmask(SIG_BLOCK, &set, &old) == 0, "block signal for rejection");
  check(lsc_read32(map, page, map, &output) == LSC_REJECTED, "blocked signal rejected");
  check(pthread_sigmask(SIG_SETMASK, &old, NULL) == 0, "restore mask");
  check(mprotect(map, page, PROT_NONE) == 0, "protect read");
  output = UINT32_C(0xdeadbeef);
  struct lsc_fault fault;
  check(lsc_read32(map, page, map, &output) == LSC_FAULT && output == UINT32_C(0xdeadbeef),
        "read fault preserves output");
  check(lsc_last_fault(&fault) && fault.signal_number == SIGSEGV && fault.signal_code == SEGV_ACCERR &&
        fault.address == (uintptr_t)map && fault.instruction == (uintptr_t)lsc_read_site &&
        fault.operation == LSC_READ && fault.count == 1 && fault.on_altstack, "read provenance");
  check(mprotect(map, page, PROT_READ | PROT_WRITE) == 0 && *(uint32_t*)map == UINT32_C(0x12345678),
        "read fault no memory effect");
  check(mprotect(map, page, PROT_READ) == 0, "protect store");
  check(lsc_write32(map, page, map, UINT32_C(0xfaceb00c)) == LSC_FAULT,
        "store fault returns explicitly");
  check(lsc_last_fault(&fault) && fault.operation == LSC_WRITE && fault.count == 2 &&
        fault.instruction == (uintptr_t)lsc_write_site && fault.on_altstack &&
        *(uint32_t*)map == UINT32_C(0x12345678), "fault store has no write");
  check(mprotect(map, page, PROT_READ | PROT_WRITE) == 0 &&
        lsc_write32(map, page, map, UINT32_C(0xfaceb00c)) == LSC_OK &&
        *(uint32_t*)map == UINT32_C(0xfaceb00c), "fresh store after repair");
  check(munmap(map, page) == 0 && lsc_detach() == 0, "mapping and stack cleanup");
  threads_test();
  check(lsc_uninstall() == 0 && sigaction(SIGSEGV, NULL, &after) == 0 && same_action(&before, &after),
        "exact saved action restored");
  check(lsc_install() == 0 && lsc_uninstall() == 0, "repeat lifecycle");
}
static void conflicts(void) {
  struct sigaction before, after;
  set_action(SIG_IGN);
  check(sigaction(SIGSEGV, NULL, &before) == 0 && lsc_install() == EBUSY &&
        sigaction(SIGSEGV, NULL, &after) == 0 && same_action(&before, &after), "ignore owner preserved");
  set_action(ignored_handler);
  check(sigaction(SIGSEGV, NULL, &before) == 0 && lsc_install() == EBUSY &&
        sigaction(SIGSEGV, NULL, &after) == 0 && same_action(&before, &after), "custom owner preserved");
}
static void replaced(void) {
  set_action(SIG_DFL);
  check(lsc_install() == 0, "install for replacement case");
  set_action(SIG_IGN);
  check(lsc_uninstall() == EBUSY, "replaced owner not overwritten");
  struct sigaction current;
  check(sigaction(SIGSEGV, NULL, &current) == 0 && current.sa_handler == SIG_IGN,
        "replacement remains installed");
}
static double now_ns(void) {
  struct timespec t;
  check(clock_gettime(CLOCK_MONOTONIC, &t) == 0, "benchmark clock");
  return (double)t.tv_sec * 1e9 + (double)t.tv_nsec;
}
static void benchmark(void) {
  // Synthetic batches, no warmup subtraction; include complete named operations.
  const unsigned cycles = 1000, stacks = 100, accesses = 10000;
  double start = now_ns();
  for (unsigned i = 0; i < cycles; ++i)
    check(lsc_install() == 0 && lsc_uninstall() == 0, "benchmark lifecycle");
  double lifecycle = (now_ns() - start) / cycles;
  check(lsc_install() == 0, "benchmark install");
  start = now_ns();
  for (unsigned i = 0; i < stacks; ++i)
    check(lsc_attach() == 0 && lsc_detach() == 0, "benchmark stacks");
  double stack_cost = (now_ns() - start) / stacks;
  check(lsc_attach() == 0, "benchmark attach");
  size_t page = page_size();
  void* map = page_new(page);
  uint32_t value = 0;
  start = now_ns();
  for (unsigned i = 0; i < accesses; ++i)
    check(lsc_read32(map, page, map, &value) == LSC_OK, "benchmark normal access");
  double normal_cost = (now_ns() - start) / accesses;
  check(mprotect(map, page, PROT_NONE) == 0, "benchmark protect");
  start = now_ns();
  for (unsigned i = 0; i < cycles; ++i)
    check(lsc_read32(map, page, map, &value) == LSC_FAULT, "benchmark capture return");
  double fault_cost = (now_ns() - start) / cycles;
  check(munmap(map, page) == 0 && lsc_detach() == 0 && lsc_uninstall() == 0,
        "benchmark teardown");
  printf("LSC_BENCH ns_per_operation lifecycle_pair=%.3f n=%u stack_pair=%.3f n=%u "
         "normal_checked_read=%.3f n=%u capture_return=%.3f n=%u\n",
         lifecycle, cycles, stack_cost, stacks, normal_cost, accesses, fault_cost, cycles);
}
static void fatal(const char* mode) {
  check(lsc_install() == 0 && lsc_attach() == 0, "fatal setup");
  size_t page = page_size();
  void* map = page_new(page);
  if (!strcmp(mode, "terminal")) lsc_terminal();
  if (!strcmp(mode, "host-null")) (void)lsc_wrong_leaf(NULL);
  if (!strcmp(mode, "host-outside")) {
    void* outside = page_new(page);
    check(mprotect(outside, page, PROT_NONE) == 0, "protect outside page");
    (void)lsc_wrong_leaf(outside);
  }
  if (!strcmp(mode, "unarmed")) {
    check(mprotect(map, page, PROT_NONE) == 0, "protect unarmed page");
    (void)lsc_wrong_leaf(map);
  }
  if (!strcmp(mode, "wrong-site")) {
    check(mprotect(map, page, PROT_NONE) == 0, "protect wrong-site page");
    lsc_test_wrong_site(map, page, map);
  }
  if (!strcmp(mode, "reentrant")) {
    check(mprotect(map, page, PROT_NONE) == 0, "protect reentrant page");
    lsc_test_reentrant(1);
    uint32_t output = 0;
    (void)lsc_read32(map, page, map, &output);
  }
  check(0, "fatal operation unexpectedly returned");
}
int main(int argc, char** argv) {
  struct rlimit no_core = {0, 0};
  check(setrlimit(RLIMIT_CORE, &no_core) == 0, "disable core dumps");
  check(argc == 2, "exactly one mode");
  if (!strcmp(argv[1], "ordinary")) test_ordinary();
  else if (!strcmp(argv[1], "normal")) normal();
  else if (!strcmp(argv[1], "conflicts")) conflicts();
  else if (!strcmp(argv[1], "replaced")) replaced();
  else if (!strcmp(argv[1], "benchmark")) benchmark();
  else fatal(argv[1]);
  printf("LSC_LIFECYCLE PASS mode=%s checks=%u\n", argv[1], checks);
  return 0;
}
