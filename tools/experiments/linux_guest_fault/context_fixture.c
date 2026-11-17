// Separate GNU/Linux x86-64 signal-context probe.  No SDK/game dependency.
#define _GNU_SOURCE 1
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <ucontext.h>
#include <unistd.h>

#if !defined(__linux__) || !defined(__x86_64__)
#error Linux x86-64 required
#endif

struct context_snapshot {
  uint64_t rsp_before, rsp_after;
  uint64_t rbx, rbp, r12, r13, r14, r15, redzone;
  uint64_t flags_before, flags_after;
  uint32_t mx_expected, mx_actual;
  uint16_t cw_expected, cw_actual;
  uint8_t padding[12], xmm0[16], xmm15[16];
};
_Static_assert(offsetof(struct context_snapshot, mx_expected) == 88, "assembly ABI");
_Static_assert(offsetof(struct context_snapshot, cw_expected) == 96, "assembly ABI");
_Static_assert(offsetof(struct context_snapshot, xmm0) == 112, "assembly ABI");
_Static_assert(offsetof(struct context_snapshot, xmm15) == 128, "assembly ABI");
extern void lgf_context_probe(const void *, struct context_snapshot *);
extern const unsigned char lgf_context_fault_site[], lgf_context_recovery[];

static uintptr_t alt_low, alt_high, protected_address;
static volatile sig_atomic_t fault_count, on_altstack, usr1_count, chain_count;
static struct sigaction prior_usr1;
static const uint32_t default_mxcsr = 0x1f80;

static void usr1_handler(int sig, siginfo_t *info, void *uc) {
  (void)info; (void)uc;
  if (sig == SIGUSR1) ++usr1_count;
}

// Deliberately narrow same-signal stand-in: prior action is our own SA_SIGINFO
// handler with empty mask, no SA_RESETHAND/SA_NODEFER. This is not a general
// sigaction chaining implementation and never invokes an unknown SDK handler.
static void chained_usr1_handler(int sig, siginfo_t *info, void *uc) {
  ++chain_count;
  prior_usr1.sa_sigaction(sig, info, uc);
}

static void fault_handler(int sig, siginfo_t *info, void *opaque) {
  volatile unsigned char marker = 0;
  ucontext_t *uc = (ucontext_t *)opaque;
  uintptr_t stack_marker = (uintptr_t)&marker;
  if (sig != SIGSEGV || !info || !uc || info->si_code != SEGV_ACCERR ||
      (uintptr_t)info->si_addr != protected_address ||
      (uintptr_t)uc->uc_mcontext.gregs[REG_RIP] != (uintptr_t)lgf_context_fault_site ||
      (uintptr_t)uc->uc_mcontext.gregs[REG_RDI] != protected_address ||
      (uc->uc_mcontext.gregs[REG_ERR] & (2 | 16)) != 0 || fault_count != 0)
    _exit(91);
  on_altstack = stack_marker >= alt_low && stack_marker < alt_high;
  ++fault_count;
  // Deliberately disturb host FP control and vectors in the handler. Kernel
  // signal return must restore the *interrupted* state from its own frame.
  __asm__ volatile("fninit\n\tldmxcsr %0\n\tpxor %%xmm0, %%xmm0\n\t"
                   "pxor %%xmm15, %%xmm15" :: "m"(default_mxcsr)
                   : "xmm0", "xmm15", "memory");
  uc->uc_mcontext.gregs[REG_RIP] = (greg_t)(uintptr_t)lgf_context_recovery;
}

static void check(int ok, const char *name) {
  if (!ok) { fprintf(stderr, "LGF_CONTEXT FAIL: %s\n", name); exit(1); }
}

int main(void) {
  struct rlimit no_core = {0, 0};
  check(setrlimit(RLIMIT_CORE, &no_core) == 0, "disable core dumps");
  long page_long = sysconf(_SC_PAGESIZE), min_stack = sysconf(_SC_MINSIGSTKSZ);
  check(page_long > 0 && min_stack > 0, "system sizes");
  size_t page = (size_t)page_long, usable = 1024u * 1024u;
  if ((size_t)min_stack > usable) usable = (size_t)min_stack;
  check(usable <= SIZE_MAX - 2 * page, "stack size overflow");
  usable = (usable + page - 1) / page * page;
  size_t total = usable + page;
  void *map = mmap(NULL, total, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  check(map != MAP_FAILED, "map altstack");
  check(mprotect(map, page, PROT_NONE) == 0, "guard altstack");
  alt_low = (uintptr_t)map + page;
  alt_high = alt_low + usable;
  stack_t stack = {0}, old_stack;
  stack.ss_sp = (void *)alt_low; stack.ss_size = usable;
  check(sigaltstack(&stack, &old_stack) == 0, "install altstack");

  void *fault_page = mmap(NULL, page, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  check(fault_page != MAP_FAILED, "map protected page");
  protected_address = (uintptr_t)fault_page;
  struct sigaction segv = {0}, old_segv, usr1 = {0}, old_usr1;
  usr1.sa_sigaction = usr1_handler; usr1.sa_flags = SA_SIGINFO;
  check(sigemptyset(&usr1.sa_mask) == 0 && sigaction(SIGUSR1, &usr1, &old_usr1) == 0,
        "install independent SIGUSR1 owner");
  struct sigaction chain = {0};
  chain.sa_sigaction = chained_usr1_handler; chain.sa_flags = SA_SIGINFO;
  check(sigemptyset(&chain.sa_mask) == 0 &&
        sigaction(SIGUSR1, &chain, &prior_usr1) == 0 &&
        (prior_usr1.sa_flags & SA_SIGINFO) && prior_usr1.sa_sigaction == usr1_handler,
        "install explicit known-handler chain");
  segv.sa_sigaction = fault_handler; segv.sa_flags = SA_SIGINFO | SA_ONSTACK;
  check(sigemptyset(&segv.sa_mask) == 0 && sigaction(SIGSEGV, &segv, &old_segv) == 0,
        "install SIGSEGV handler");
  sigset_t original, unblock, before, after;
  check(sigemptyset(&unblock) == 0 && sigaddset(&unblock, SIGUSR1) == 0 &&
        sigaddset(&unblock, SIGSEGV) == 0 &&
        sigprocmask(SIG_UNBLOCK, &unblock, &original) == 0, "unblock test signals");
  check(raise(SIGUSR1) == 0 && usr1_count == 1 && chain_count == 1,
        "prior SIGUSR1 handler chained exactly once");
  sigset_t block_usr1;
  check(sigemptyset(&block_usr1) == 0 && sigaddset(&block_usr1, SIGUSR1) == 0 &&
        sigprocmask(SIG_BLOCK, &block_usr1, NULL) == 0 &&
        sigprocmask(SIG_SETMASK, NULL, &before) == 0, "set test mask");

  struct context_snapshot s = {0};
  lgf_context_probe(fault_page, &s);
  check(sigprocmask(SIG_SETMASK, NULL, &after) == 0, "read restored mask");
  check(fault_count == 1 && on_altstack, "one fault on alternate stack");
  check(sigismember(&before, SIGUSR1) == 1 && sigismember(&after, SIGUSR1) == 1 &&
        sigismember(&before, SIGSEGV) == 0 && sigismember(&after, SIGSEGV) == 0,
        "signal mask restored");
  check(s.rsp_before == s.rsp_after && (s.rsp_before & 15u) == 8u &&
        (s.rsp_after < alt_low || s.rsp_after >= alt_high),
        "normal stack pointer and alignment restored");
  check(s.rbx == UINT64_C(0x1122334455667788) && s.rbp == UINT64_C(0x2233445566778899) &&
        s.r12 == UINT64_C(0x33445566778899aa) && s.r13 == UINT64_C(0x445566778899aabb) &&
        s.r14 == UINT64_C(0x5566778899aabbcc) && s.r15 == UINT64_C(0x66778899aabbccdd),
        "callee-saved GPR sentinels");
  check(s.redzone == UINT64_C(0x78abcdef12345609), "red zone preserved");
  check((s.flags_before & 1) && (s.flags_after & 1), "carry flag restored");
  check(s.mx_actual == s.mx_expected && s.cw_actual == s.cw_expected, "FP control restored");
  const uint64_t x0[2] = {UINT64_C(0x0123456789abcdef), UINT64_C(0xfedcba9876543210)};
  const uint64_t x15[2] = {UINT64_C(0x13579bdf2468ace0), UINT64_C(0x02468ace13579bdf)};
  check(memcmp(s.xmm0, x0, 16) == 0 && memcmp(s.xmm15, x15, 16) == 0,
        "interrupted XMM0/XMM15 restored");

  check(sigprocmask(SIG_UNBLOCK, &block_usr1, NULL) == 0 &&
        raise(SIGUSR1) == 0 && usr1_count == 2 && chain_count == 2,
        "independent SIGUSR1 chain survives");
  check(sigaction(SIGSEGV, &old_segv, NULL) == 0 &&
        sigaction(SIGUSR1, &old_usr1, NULL) == 0 &&
        sigprocmask(SIG_SETMASK, &original, NULL) == 0, "restore actions and mask");
  stack_t disabled = {0}; disabled.ss_flags = SS_DISABLE;
  check(sigaltstack(&disabled, NULL) == 0 && sigaltstack(&old_stack, NULL) == 0,
        "restore altstack");
  check(munmap(fault_page, page) == 0 && munmap(map, total) == 0, "unmap fixtures");
  puts("LGF_CONTEXT PASS");
  return 0;
}
